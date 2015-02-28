from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.core.exceptions import ObjectDoesNotExist
import json
import random
import math
import collections
from packgen.models import draft_picks, draft_record, all_cards, KTK_Reg_Coef
from django.db.models import Max, Count, F
import draft_algos

###### define functions

#player_id (position) and pick number determines which pack they should pick from
#remember that directions switch on second pack
def find_pack_id(player_id, pick_num):

    if pick_num <= 15: #Pass right
        pack_id = 1 + (player_id + pick_num - 1) % 8

    elif pick_num <= 30: #Pass Left.
        pick_num = pick_num - 15
        pack_id =  16 - (pick_num + 6 - player_id) % 8

    else: #Pass Right again.
        pick_num = pick_num - 30 #map down
        pack_id = 1 + (player_id + pick_num - 1) % 8
        pack_id = pack_id + 16 #map back

    return(pack_id)

#AI makes picks
def AI_next_picks(new_draft_record, pick_num):
    #loop through AI players
    for player_id in range(1,8):
        #determine cards each player has picked
        prev_picks = draft_picks.objects.filter(draft_record=new_draft_record, player_id=player_id)

        #determine cards in current pack
        current_pack_id = find_pack_id(player_id, pick_num)
        current_pack = draft_picks.objects.filter(draft_record=new_draft_record, pack_id=current_pack_id, pick_num=0)
        #current_pack = cards_in_pack(new_draft_record, current_pack_id)

        #get card ratings
        card_ratings = draft_algos.pick_algorithm_rules(prev_picks, current_pack, pick_num)


        #make into list and sort by rating
        mtg_pack = []
        for item in card_ratings:
            tmp_list = item[1]
            tmp_list.append(item[0])
            mtg_pack.append(tuple(tmp_list))
        mtg_pack.sort(key = lambda tup: tup[0], reverse=True)
        
        #Save computer pick
        this_pick = draft_picks.objects.get(draft_record=new_draft_record, pack_id=current_pack_id, card_id=mtg_pack[0][1], card_index=mtg_pack[0][2])
        #this_pick = draft_picks.objects.filter(draft_record=new_draft_record, pack_id=current_pack_id, card_id=card_ratings[len(card_ratings)-1][0])[0]

        this_pick.pick_num = pick_num
        this_pick.player_id = player_id
        this_pick.save()


#Input: draft_record, 3 set codes, 1 for each pack
#Output: List of card objects for first pack
def pack_gen(new_draft_record, sets=[]):
    pack_id = 1

    for set_code in sets:
        mythics = all_cards.objects.filter(set_code=set_code, rarity='Mythic Rare').exclude(basic_land_slot=1).values_list('multiverseid', flat=True)
        rares = all_cards.objects.filter(set_code=set_code, rarity='Rare').exclude(basic_land_slot=1).values_list('multiverseid', flat=True)
        uncommons = all_cards.objects.filter(set_code=set_code, rarity='Uncommon').exclude(basic_land_slot=1).values_list('multiverseid', flat=True)
        commons = all_cards.objects.filter(set_code=set_code, rarity='Common').exclude(basic_land_slot=1).values_list('multiverseid', flat=True)
        basic_lands = all_cards.objects.filter(set_code=set_code, basic_land_slot=1).values_list('multiverseid', flat=True)

        #generate 8 packs
        for x in range(0,8):
            pack = []
            
            #check for mythic
            if random.randint(1,8) == 8:
                pack.append(random.choice(mythics))
            else:
                pack.append(random.choice(rares))

            #add commons and uncommons
            pack.extend(random.sample(uncommons, 3))
            pack.extend(random.sample(commons, 10))

            #check for foil
            if random.randint(1,4) == 4:
                if random.randint(1,8*14) == 1:
                    pack[13] = random.choice(mythics)
                elif random.randint(1,14) == 1:
                    pack[13] = random.choice(rares)
                elif random.randint(1,5) == 1:
                    pack[13] = random.choice(uncommons)
                else:
                    pack[13] = random.choice(commons)

            #add basic land
            pack.append(random.choice(basic_lands))

            #store cards in pack
            index = 1
            for card_id in pack:
                card = draft_picks(draft_record=new_draft_record, pack_id=pack_id, card_index=index, card_id=all_cards.objects.get(set_code=set_code, multiverseid=card_id))
                card.save()
                index += 1
              
            pack_id += 1

######define views

#generate packs and initialize when draft first starts
def start_draft(request, set1, set2, set3):
    #initialize some variables
    draft_sets = [set1, set2, set3]
    request.session['pick_num'] = 1
    pick_num = 1

    #assign draft_id.
    new_draft_id = draft_record.objects.count() + 1
    request.session['draft_id'] = new_draft_id

    #create draft record
    new_draft = draft_record(draft_id=new_draft_id, draft_set=''.join(draft_sets))
    new_draft.save()

    #create 24 draft packs
    pack_gen(new_draft, draft_sets)
    first_pack = draft_picks.objects.filter(draft_record=new_draft, pack_id=1, pick_num=0)

    #get card ratings
    card_ratings = draft_algos.pick_algorithm_rules([], first_pack, pick_num)

    #make into list of tuples
    mtg_pack = []
    for item in card_ratings:
        tmp_list = item[1]
        tmp_list.append(item[0])
        mtg_pack.append(tuple(tmp_list))

    #sort by rating
    mtg_pack.sort(key = lambda tup: tup[0], reverse=True)
    computer_pick = first_pack.filter(card_index=mtg_pack[0][2])[0]

    #store card ratings so we don't need to recalculate again when updating card coefficients
    request.session['pack_ratings'] = mtg_pack

    #display info
    #sort by index
    mtg_pack.sort(key = lambda tup: tup[2])

    #pass list of card objects corresponding to player 0, pack 1
    context = {'mtg_pack': mtg_pack, 'draft_id': new_draft_id, 'comp_pick' : computer_pick.card_id.name, 'draft_set' : ''.join(draft_sets)}
    
    return render(request, 'packgen/packgen.html', context)


#continuation of draft, with AI
def draft_card(request, pick_index):

    #check pick_index is valid
    if int(pick_index) < 1 or int(pick_index) > 15:
        return HttpResponseNotFound('<h1>Invalid Pick</h1>')

    #reconstruct draft from draft_id. Human is player 0
    player_id = 0

    #check if draft_id valid
    try:
         draft_id = request.session['draft_id']
    except KeyError:
        return HttpResponseNotFound('<h1>Invalid Draft_Id. Please clear cache and try again.</h1>')

    pick_num = int(request.session['pick_num'])

    #find draft
    new_draft_record = draft_record.objects.get(draft_id=draft_id)

    #record computer picks
    AI_next_picks(new_draft_record, pick_num)
    
    #find id of current pack
    pack_id = find_pack_id(player_id, pick_num)

    #fetch current pick
    this_pick = draft_picks.objects.get(draft_record=new_draft_record, pack_id=pack_id, card_index=pick_index)

    #check if pick is valid: i.e. does pick_num=0
    if this_pick.pick_num != 0:
        return HttpResponseNotFound('<h1>Pick Error. Card selected has already been picked. Please choose another card.</h1>')

    #record current pick
    this_pick.pick_num = pick_num
    this_pick.player_id = player_id
    this_pick.save()

    #update card ratings as needed based on pick information
    draft_algos.update_coefficients(pick_num, request.session['pack_ratings'], pick_index)

    if pick_num >= 45: #last pick. Display all players and picks
        all_picks = []
        for player in range(0,8):
            prev_picks = draft_picks.objects.filter(draft_record=new_draft_record, player_id=player).order_by('pick_num')
            all_picks.append(prev_picks)

        context = {'cards_drafted': all_picks, 'draft_id' : draft_id, 'draft_set' : new_draft_record.draft_set}
        return render(request, 'packgen/end_draft.html', context)

    else:
        #update previous picks to display
        updated_picks = draft_picks.objects.filter(draft_record=new_draft_record, player_id=player_id)

        #separate picks by color
        multicolor_picks = updated_picks.filter(card_id__red_ind__gt=1-F('card_id__blue_ind')-F('card_id__green_ind')-F('card_id__white_ind')-F('card_id__black_ind'))
        colorless_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=0)
        red_picks = updated_picks.filter(card_id__red_ind=1, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=0)
        green_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=1, card_id__white_ind=0, card_id__black_ind=0)
        blue_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=1, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=0)
        black_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=1)
        white_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=1, card_id__black_ind=0)
        
        #increment picks
        pick_num = pick_num + 1
        request.session['pick_num'] = pick_num

        #determine next pack to display
        pack_id = find_pack_id(player_id, pick_num)
        next_pack = draft_picks.objects.filter(draft_record=new_draft_record, pack_id=pack_id, pick_num=0)

        #get card ratings and indices as dict
        card_ratings = draft_algos.pick_algorithm_rules(updated_picks, next_pack, pick_num)

        #make into list of tuples
        mtg_pack = []
        for item in card_ratings:
            tmp_list = item[1]
            tmp_list.append(item[0])
            mtg_pack.append(tuple(tmp_list))

        #sort by rating
        mtg_pack.sort(key = lambda tup: tup[0], reverse=True)
        computer_pick = next_pack.filter(card_index=mtg_pack[0][2])[0]

        #store card ratings so we don't need to recalculate again when updating card coefficients
        request.session['pack_ratings'] = mtg_pack

        #display info
        #sort by index
        mtg_pack.sort(key = lambda tup: tup[2])
        pack_display = int(math.ceil(pick_num/float(15)))
        pick_display= (pick_num - 1) % 15 + 1


        context = {'draft_set' : new_draft_record.draft_set, 'multicolor_picks': multicolor_picks,  'mtg_pack': mtg_pack, 'draft_id' : draft_id, \
                    'comp_pick' : computer_pick.card_id.name, 'pack_display' : pack_display, 'pick_display' : pick_display, 'red_picks' : red_picks, \
                    'white_picks' : white_picks, 'blue_picks' : blue_picks, 'green_picks' : green_picks, 'black_picks' : black_picks, 'colorless_picks' : colorless_picks}
        return render(request, 'packgen/draft.html', context)


def draft_review(request, draft_id, player_number, pick_num):

    #check valid draft id
    try:
        new_draft_record = draft_record.objects.get(draft_id=draft_id)
    except ObjectDoesNotExist:
        return HttpResponseNotFound('<h1>Draft_Id Does not exist.</h1>')

    pick_num = int(pick_num)
    player_id = int(player_number) - 1

    #check valid pick_num and player_number
    if player_id < 0 or player_id > 7:
        return HttpResponseNotFound('<h1>Invalid Player Number</h1>')

    if pick_num < 1 or pick_num > 45:
        all_picks = []
        for player in range(0,8):
            prev_picks = draft_picks.objects.filter(draft_record=new_draft_record, player_id=player).order_by('pick_num')
            all_picks.append(prev_picks)

        context = {'cards_drafted': all_picks, 'draft_id' : draft_id, 'draft_set' : new_draft_record.draft_set}
        return render(request, 'packgen/end_draft.html', context)

    #Exclude all picks greater than pick_num
    updated_picks = draft_picks.objects.filter(draft_record=new_draft_record, player_id=player_id).exclude(pick_num__gte=pick_num)

    #separate picks by color
    multicolor_picks = updated_picks.filter(card_id__red_ind__gt=1-F('card_id__blue_ind')-F('card_id__green_ind')-F('card_id__white_ind')-F('card_id__black_ind'))
    colorless_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=0)
    red_picks = updated_picks.filter(card_id__red_ind=1, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=0)
    green_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=1, card_id__white_ind=0, card_id__black_ind=0)
    blue_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=1, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=0)
    black_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=0, card_id__black_ind=1)
    white_picks = updated_picks.filter(card_id__red_ind=0, card_id__blue_ind=0, card_id__green_ind=0, card_id__white_ind=1, card_id__black_ind=0)
    
    try: 
        player_pick = draft_picks.objects.get(draft_record=new_draft_record, player_id=player_id, pick_num=pick_num)
    except ObjectDoesNotExist:
        all_picks = []
        for player in range(0,8):
            prev_picks = draft_picks.objects.filter(draft_record=new_draft_record, player_id=player).order_by('pick_num')
            all_picks.append(prev_picks)

        context = {'cards_drafted': all_picks, 'draft_id' : draft_id, 'draft_set' : new_draft_record.draft_set}
        return render(request, 'packgen/end_draft.html', context)

    #determine pack to display
    pack_id = find_pack_id(player_id, pick_num)
    this_pack = draft_picks.objects.filter(draft_record=new_draft_record, pack_id=pack_id).exclude(pick_num__range=(1, pick_num - 1))
    pack_display = int(math.ceil(pick_num/float(15)))
    pick_display= (pick_num - 1) % 15 + 1

    context = {'draft_set' : new_draft_record.draft_set, 'multicolor_picks': multicolor_picks,  'mtg_pack': this_pack, 'draft_id' : draft_id, 'player_display' : player_number, \
                    'player_pick' : player_pick.card_id.name, 'pack_display' : pack_display, 'pick_display' : pick_display, 'red_picks' : red_picks, \
                    'white_picks' : white_picks, 'blue_picks' : blue_picks, 'green_picks' : green_picks, \
                    'black_picks' : black_picks, 'colorless_picks' : colorless_picks, 'next_pick' : pick_num + 1, 'prev_pick' : pick_num -1}
    return render(request, 'packgen/draft_review.html', context)

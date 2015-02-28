from packgen.models import draft_picks, draft_record, all_cards, KTK_Reg_Coef
from django.db.models import Sum
import math

###### define functions

#take prev_picks and current_pack as a queryset of draft_picks. This contains all cards previously drafted as well as cards in the pack
#return list of tuples of multiverse_id and rating
def pick_algorithm_rules(prev_picks, current_pack, pick_num):

    #tuning parameters.
    color_tune = float(5)/42 * pick_num #How important color matching is. Higher is better. 
    color_offset = 1/float(pick_num) #prevent score to be 0 if no colors match.
    fixer_tune = float(5)/42 * pick_num #How important fixer matching is. Higher is better. 
    color_dist = float(1)/3 # 1=favor mono color. 1/2 = favor 2-color. 1/3 = favor 3-color

    #adjust for color importance. Normally depends on cards already drafted. However, can offset to preferentially draft a color
    blue_lean = float(0)
    red_lean = float(0)
    green_lean = float(0)
    black_lean = float(0)
    white_lean = float(0)
    blue_fix = float(0)
    red_fix = float(0)
    green_fix = float(0)
    black_fix = float(0)
    white_fix = float(0)

    card_ratings = {}
    for card in current_pack:
        card_ratings[card.card_index] = [card.card_id.limited_rating, card.card_id.multiverseid] #within a pack, card index uniquely identifies a card

    if pick_num == 1: #first few picks, use rating only
        return(card_ratings.items())
    else: #apply penalities for not sharing color with cards already drafted
        
        if pick_num < 9:
            usable_count = pick_num
        elif pick_num < 15: #pack 2
            usable_count = 8
        elif pick_num < 23:
            usable_count = pick_num - 6
        elif pick_num < 29: #pack 3
            usable_count = 15
        elif pick_num < 37:
            usable_count = pick_num - 12
        else:
            usable_count = 21

        playables = prev_picks.filter(card_id__land_ind=0).order_by('-card_id__limited_rating')[:usable_count] #Take top usable_count cards in pool
        cards_in_contention = current_pack.filter(card_id__limited_rating__gte = 0) #filter out cards in pack with rating < 0. Set to -99 in dataset.

        for pick in playables: #see how many cards in each color
            blue_lean += pick.card_id.blue_ind
            black_lean += pick.card_id.black_ind
            white_lean += pick.card_id.white_ind
            red_lean += pick.card_id.red_ind
            green_lean += pick.card_id.green_ind
            blue_fix += pick.card_id.ufix_ind
            red_fix += pick.card_id.rfix_ind
            green_fix += pick.card_id.gfix_ind
            black_fix += pick.card_id.bfix_ind
            white_fix += pick.card_id.wfix_ind

        color_total = blue_lean + black_lean + white_lean + green_lean + red_lean + 1 #add 1 to avoid divide by 0

        # if max(blue_lean, black_lean, white_lean, green_lean, red_lean)/color_total > 0.6: #if we are mostly one color
        #     color_tune = mono_adj #reduce importance of color matching

        for card in cards_in_contention: #update rating based on color penalties
            if card.card_id.fixer_ind == 0: #if not a fixer, do color adjustment and curve adjustment
                #if all cards in pool are (color), and card is (color): rating + 1. If no cards in pool are (color) and card is (color), rating -1
                #scale adjustments by pick_num. As we get further into the draft, color matching matters more
                #color importance might also depend on what fixers we already have
                
                #0 for perfect color matching. 5 for no color matching. Color_dist controls color equilibrium
                color_adjustment = abs(color_dist * card.card_id.blue_ind - (blue_lean + blue_fix/2)/color_total) + \
                                    abs(color_dist * card.card_id.red_ind - (red_lean + red_fix/2)/color_total) + \
                                    abs(color_dist * card.card_id.green_ind - (green_lean + green_fix/2)/color_total) + \
                                    abs(color_dist * card.card_id.white_ind - (white_lean + white_fix/2)/color_total) + \
                                    abs(color_dist * card.card_id.black_ind - (black_lean + black_fix/2)/color_total)

                card_ratings[card.card_index][0] -= round(color_tune * color_adjustment, 2)

                #adjust for mana curve

            else: 
                fixer_adjustment = card.card_id.ufix_ind * max(blue_lean - blue_fix, 0)/color_total + \
                                    card.card_id.rfix_ind * max(red_lean - red_fix, 0)/color_total + \
                                    card.card_id.gfix_ind * max(green_lean - green_fix, 0)/color_total + \
                                    card.card_id.wfix_ind * max(white_lean - white_fix, 0)/color_total + \
                                    card.card_id.bfix_ind * max(black_lean - black_fix, 0)/color_total
                
                 #if card was not previously adjusted
                card_ratings[card.card_index][0] -= round(fixer_tune * (1.3 - fixer_adjustment), 2) 
             
            card_ratings[card.card_index][0] = round(card_ratings[card.card_index][0], 2)
        return(card_ratings.items())

#card_ratings is list of tuples (rating, card_id, card_index) sorted by rating with [0] having the highest rating
def update_coefficients(pick_num=1, card_ratings=[], pick_index=1):
    learn_rate = 0.01 #amount to change card rating after incorrect prediction
    pick_num = int(pick_num)
    pick_index = int(pick_index)

    if pick_num == 1: #on first pick, alter card limited_rating
        counter = 0
        for card in card_ratings:
            print(card)
            this_card = all_cards.objects.get(multiverseid=card[1])
            if card[2] == pick_index: #if card has same index as chosen card .., remember this is sorted by rating, so if chosen card was predicted correctly, we are good
                if counter != 0: #if there is 1 or more cards with rating higher than chosen card ...
                    this_card.limited_rating += learn_rate #update limited rating
                    this_card.save()
                break
            else: #otherwise, decrement ratings of wrong cards
                this_card.limited_rating -= learn_rate #update limited rating
                this_card.save()
            counter += 1

#linear regression pick algorithm
#takes dictionary of card : count and cards in pack as list of multiverseid's
def pick_algorithm_lm(card_counts={}, current_pack=[]):
    card_ratings = {}

    for card in current_pack:
        card_of_interest = KTK_Reg_Coef.objects.filter(main_card=card)
        rating = card_of_interest.filter(reg_card='limited_rating').values_list('reg_coef', flat=True)[0]

        for key, value in card_counts.iteritems():
            rating = rating + value * card_of_interest.filter(reg_card=key).values_list('reg_coef', flat=True)[0]

        card_ratings[card] = rating
        #print(card_ratings)

    return(card_ratings)


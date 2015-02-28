from django.db import models

# Create your models here.

class all_cards(models.Model):
    name = models.TextField(primary_key=True)
    multiverseid = models.IntegerField(primary_key=True)
    set_code = models.CharField(max_length=3)
    cmc = models.IntegerField(blank=True, null=True)
    rarity = models.TextField()
    white_ind = models.IntegerField(blank=True, null=True)
    blue_ind = models.IntegerField(blank=True, null=True)
    black_ind = models.IntegerField(blank=True, null=True)
    red_ind = models.IntegerField(blank=True, null=True)
    green_ind = models.IntegerField(blank=True, null=True)
    artifact_ind = models.IntegerField(blank=True, null=True)
    creature_ind = models.IntegerField(blank=True, null=True)
    enchantment_ind = models.IntegerField(blank=True, null=True)
    instant_ind = models.IntegerField(blank=True, null=True)
    sorcery_ind = models.IntegerField(blank=True, null=True)
    planeswalker_ind = models.IntegerField(blank=True, null=True)
    land_ind = models.IntegerField(blank=True, null=True)
    limited_rating = models.DecimalField(max_digits=5, decimal_places=3)
    fixer_ind = models.IntegerField(blank=True, null=True)
    wfix_ind = models.IntegerField(blank=True, null=True)
    ufix_ind = models.IntegerField(blank=True, null=True)
    bfix_ind = models.IntegerField(blank=True, null=True)
    rfix_ind = models.IntegerField(blank=True, null=True)
    gfix_ind = models.IntegerField(blank=True, null=True)
    basic_land_slot = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'all_cards'

    def __str__(self):
        return str(self.multiverseid)

class KTK_Reg_Coef(models.Model):
    main_card = models.TextField(primary_key=True)
    reg_card = models.TextField(primary_key=True)
    reg_coef = models.DecimalField(max_digits=5, decimal_places=3)

    class Meta:
        managed = False
        db_table = 'KTK_reg_coef'

class draft_record(models.Model):
    draft_id = models.IntegerField(default=0, primary_key=True)
    draft_date = models.DateTimeField(auto_now=True)
    draft_set = models.CharField(max_length=10)

    def __str__(self):
        return str(self.draft_id)

class draft_picks(models.Model):
    draft_record = models.ForeignKey(draft_record)
    player_id = models.IntegerField(default=99) #players 0-7. 99 means card not yet picked
    pack_id = models.IntegerField() #1-24
    pick_num = models.IntegerField(default=0) #1-45. 0 means card not yet picked
    card_index = models.IntegerField() #0-13
    #card_id = models.CharField(max_length=6, default='000000') #multiverse id
    card_id = models.ForeignKey(all_cards)

    def __str__(self):
        return str(self.card_id)

class rules_reg_coeff(models.Model):
    draft_set = models.CharField(max_length=10)
    color_tune = models.DecimalField(default=5, max_digits=5, decimal_places=3)
    fixer_tune = models.DecimalField(default=5, max_digits=5, decimal_places=3)

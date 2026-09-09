"""
The region folders under skins/, and how a skin is assigned to one.

Folders are OSRS world regions, not cities. Two extras:
  multi  - the skin is used in more than one region (generic NPCs, default player skins)
  other  - Tutorial Island, instanced/minigame areas, the Abyss, or genuinely unplaceable
"""

REGIONS = [
    "asgarnia",
    "feldip_hills",
    "fremennik_province",
    "great_kourend",
    "kandarin",
    "karamja",
    "kebos_lowlands",
    "kharidian_desert",
    "misthalin",
    "morytania",
    "tirannwn",
    "troll_country",
    "varlamore",
    "wilderness",
    "multi",
    "other",
]

MULTI = "multi"
OTHER = "other"

# Player skins, not NPC skins - the six starting bodies and the holiday costumes, which
# any player can wear anywhere. They were the `player/` package in the old Skins enum.
# Without this they scatter across regions on the accident of which dialogue happens to
# mention one, which is how DEFAULT_MALE_WHITE ended up in multi and DEFAULT_MALE_BLACK
# in other.
PLAYER_SKINS = {
    "DEFAULT_MALE_WHITE", "DEFAULT_MALE_TAN", "DEFAULT_MALE_BLACK",
    "DEFAULT_FEMALE_WHITE", "DEFAULT_FEMALE_TAN", "DEFAULT_FEMALE_BLACK",
    "MALE_JACK_LANTERN", "FEMALE_JACK_LANTERN",
    "MALE_SKELETON", "FEMALE_SKELETON",
}

# The dialogue tree in MineScape-me/MineScape is filed by city, which is a much stronger
# signal than a wiki lookup: it says where *this server* actually uses the skin. This maps
# those city folders onto the region they sit in.
CITY_TO_REGION = {
    "abyss": OTHER,                      # reached through the Wilderness, but its own plane
    "alkharid": "kharidian_desert",      # Al Kharid is desert, not Misthalin
    "barbarian_village": "misthalin",
    "baxtorian": "kandarin",
    "black_knights_fortress": "asgarnia",
    "brimhaven": "karamja",
    "burthorpe": "asgarnia",             # Troll Country starts north of here
    "camelot": "kandarin",
    "canifis": "morytania",
    "castle_wars": "kandarin",
    "catherby": "kandarin",
    "clocktower": "kandarin",
    "coal_trucks": "kandarin",
    "combat_training_camp": "kandarin",
    "cosair_cove": "feldip_hills",       # spelled this way in the dialogue tree
    "draynor": "misthalin",
    "draynor_manor": "misthalin",
    "dwarven_mine": "asgarnia",
    "east_ardougne": "kandarin",
    "edgeville": "misthalin",
    "entrana": "asgarnia",
    "falador": "asgarnia",
    "feldip_hills": "feldip_hills",
    "fight_arena": "kandarin",
    "fishing_contest": "kandarin",       # Hemenster
    "fishing_guild": "kandarin",
    "goblin_village": "asgarnia",
    "grand_exchange": "misthalin",
    "gu_tanoth": "feldip_hills",
    "ham_hideout": "misthalin",
    "ice_mountain": "asgarnia",
    "jiggig": "feldip_hills",
    "karamja": "karamja",
    "khazard_battlefield": "kandarin",
    "legends_guild": "kandarin",
    "lumbridge": "misthalin",
    "mort_myre": "morytania",
    "morytania": "morytania",
    "multi": MULTI,
    "ourania": "kandarin",
    "paterdomus": "morytania",
    "port_khazard": "kandarin",
    "port_phasmatys": "morytania",
    "port_sarim": "asgarnia",
    "ranging_guild": "kandarin",
    "rimmington": "asgarnia",
    "rogues_den": "asgarnia",
    "seers_village": "kandarin",
    "tai_bwo_wannai": "karamja",
    "taverley": "asgarnia",
    "taverley_dungeon": "asgarnia",
    "temp": OTHER,                       # scratch folder in the dialogue tree
    "tower_of_life": "kandarin",
    "tree_gnome_village": "kandarin",
    "tutorial_island": OTHER,            # not one of the world regions
    "varrock": "misthalin",
    "warriors_guild": "asgarnia",
    "west_ardougne": "kandarin",
    "wilderness": "wilderness",
    "witchaven": "kandarin",
    "wizards_tower": "misthalin",
    "yanille": "kandarin",
    "zanaris": OTHER,                     # a separate plane, not a surface region
}

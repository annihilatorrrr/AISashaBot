import pyrogram

HELP_DICTIONARY = {
    "actions_on_users": [
        "JUNIOR_MOD",
        "invite",
        "warn",
        "unwarn",
        "unwarnall",
        "kick",
        "temprestrict",
        "restrict",
        "unrestrict",
        "tempban",
        "ban",
        "unban",
        "MASTER",
        "gban",
        "ungban",
        "block",
        "unblock",
    ],
    "alternatives": ["USER", "alternatives", "cancel"],
    "bot_management": [
        "MASTER",
        "ping",
        "getip",
        "exec",
        "eval",
        "vardump",
        "reloadlangs",
        "reboot",
        "leave",
        "getstring",
        "setstring",
        "reload",
        "uptime",
        "todo",
        "botplugins",
        "gbanned",
        "blocked",
        "cancel",
    ],
    "chat_management": [
        "USER",
        "staff",
        "admins",
        "link",
        "kickme",
        "JUNIOR_MOD",
        "del",
        "welcome",
        "rules",
        "pin",
        "syncadmins",
        "settings",
        "censorships",
        "whitelistedchats",
        "whitelistedgbanned",
        "whitelisted",
        "logs",
        "sendlogs",
        "cancel",
        "SENIOR_MOD",
        "newlink",
        "setlog",
    ],
    "help": ["USER", "start", "help", "helpall"],
    "info_data": [
        "USER",
        "id",
        "username",
        "info",
        "me",
        "groups",
        "JUNIOR_MOD",
        "ismember",
    ],
    "multiple_commands": [
        "SENIOR_MOD",
        "multipleinvite",
        "multiplewarn",
        "multipleunwarn",
        "multipleunwarnall",
        "multiplekick",
        "multipletemprestrict",
        "multiplerestrict",
        "multipleunrestrict",
        "multipletempban",
        "multipleban",
        "multipleunban",
        "MASTER",
        "multiplegban",
        "multipleungban",
        "multipleblock",
        "multipleunblock",
    ],
    # "network_management": ["NETWORK_MOD"],
    "plugins_management": ["SENIOR_MOD", "plugins"],
    "user_management": ["USER", "mysettings", "cancel"],
    # OPTIONAL PLUGINS
    "dogify": ["USER", "INTRO", "doge"],
    "extra_variables": ["USER", "extras", "cancel"],
    "flame": ["JUNIOR_MOD", "flame", "stopflame"],
    "interact": ["USER", "echo", "edit", "test", "chat_action"],
    "latex": ["USER", "INTRO", "latex"],
    "misc": ["USER", "convertseconds", "convertduration"],
    # "likes": ["USER", "1up", "1down"],
    # "pokedex": ["USER", "pokemon"],
    "qrify": ["USER", "INTRO", "qrencode", "qrdecode"],
    "shout": ["USER", "shout"],
    "urban_dictionary": ["USER", "INTRO", "ud"],
    "webshot": ["USER", "INTRO", "webshot"],
}

PUNISHMENT_EMOJI = {
    0: pyrogram.Emoji.OK_BUTTON,
    1: pyrogram.Emoji.LITTER_IN_BIN_SIGN,
    2: pyrogram.Emoji.WARNING,
    3: pyrogram.Emoji.MAN_S_SHOE,
    4: pyrogram.Emoji.HOURGLASS_NOT_DONE + pyrogram.Emoji.MUTED_SPEAKER,
    5: pyrogram.Emoji.MUTED_SPEAKER,
    6: pyrogram.Emoji.HOURGLASS_NOT_DONE + pyrogram.Emoji.HAMMER,
    7: pyrogram.Emoji.HAMMER,
    pyrogram.Emoji.OK_BUTTON: 0,
    pyrogram.Emoji.LITTER_IN_BIN_SIGN: 1,
    pyrogram.Emoji.WARNING: 2,
    pyrogram.Emoji.MAN_S_SHOE: 3,
    pyrogram.Emoji.HOURGLASS_NOT_DONE + pyrogram.Emoji.MUTED_SPEAKER: 4,
    pyrogram.Emoji.MUTED_SPEAKER: 5,
    pyrogram.Emoji.HOURGLASS_NOT_DONE + pyrogram.Emoji.HAMMER: 6,
    pyrogram.Emoji.HAMMER: 7,
}


PUNISHMENT_STRING = {
    0: "nothing",
    1: "delete",
    2: "warn",
    3: "kick",
    4: "temprestrict",
    5: "restrict",
    6: "tempban",
    7: "ban",
    "nothing": 0,
    "delete": 1,
    "warn": 2,
    "kick": 3,
    "temprestrict": 4,
    "restrict": 5,
    "tempban": 6,
    "ban": 7,
}

RANKS = {
    0: "user",
    1: "privileged_user",
    2: "junior_mod",
    3: "senior_mod",
    4: "owner",
    5: "network_mod",
    6: "network_owner",
    7: "master",
    "user": 0,
    "privileged_user": 1,
    "junior_mod": 2,
    "senior_mod": 3,
    "owner": 4,
    "network_mod": 5,
    "network_owner": 6,
    "master": 7,
    "administrator": "administrator",
}


PERMISSIONS = {
    "can_change_info": "can_change_info",
    "can_delete_messages": "can_delete_messages",
    "can_invite_users": "can_invite_users",
    "can_restrict_members": "can_restrict_members",
    "can_pin_messages": "can_pin_messages",
    "can_promote_members": "can_promote_members",
}


RESTRICTIONS = {
    "can_change_info": "can_change_info",
    "can_invite_users": "can_invite_users",
    "can_pin_messages": "can_pin_messages",
    "can_send_messages": "can_send_messages",
    "can_send_media_messages": "can_send_media_messages",
    "can_send_other_messages": "can_send_other_messages",
    "can_add_web_page_previews": "can_add_web_page_previews",
    "can_send_polls": "can_send_polls",
}


YES_NO_EMOJI = {
    0: pyrogram.Emoji.BALLOT_BOX_WITH_CHECK,
    1: pyrogram.Emoji.WHITE_HEAVY_CHECK_MARK,
    pyrogram.Emoji.BALLOT_BOX_WITH_CHECK: 0,
    pyrogram.Emoji.WHITE_HEAVY_CHECK_MARK: 1,
}


RADIOBUTTON_EMOJI = {
    0: pyrogram.Emoji.WHITE_LARGE_SQUARE,
    1: pyrogram.Emoji.WHITE_SQUARE_BUTTON,
    pyrogram.Emoji.WHITE_LARGE_SQUARE: 0,
    pyrogram.Emoji.WHITE_SQUARE_BUTTON: 1,
}


SLOW_MODE_VALUES = {
    0: "0",
    1: "10",
    2: "30",
    3: "60",
    4: "300",
    5: "900",
    6: "3600",
    "0": 0,
    "10": 1,
    "30": 2,
    "60": 3,
    "300": 4,
    "900": 5,
    "3600": 6,
}
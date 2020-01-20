import datetime
import hashlib
import re
import time
import traceback
import typing

import peewee
import pyrogram

import db_management
import methods
import my_filters
import utils

punishments = {
    # chat_id = { msg.message_id or cb_qry.id = { "punishment" = 0
    #                                             "reasons" = [] }
    # }
}
flood = dict()
# check_msg temp dictionary for messages hashes to prevent shitstorms
msgsHashes = {
    # chat_id = { msgTextHash or mediaId = [] }
}
_ = utils.GetLocalizedString


def InstantiatePunishmentDictionary(chat_id: int, id_: int):
    # if chat_id not registered into the punishments dictionary register it
    if chat_id not in punishments:
        punishments[chat_id] = {}
    if id_ not in punishments[chat_id]:
        punishments[chat_id][id_] = {}
        punishments[chat_id][id_]["punishment"] = 0
        punishments[chat_id][id_]["reasons"] = []


def ChangePunishmentAddReason(chat_id: int, id_: int, punishment: int, reason: str):
    punishments[chat_id][id_]["punishment"] = max(
        punishment, punishments[chat_id][id_]["punishment"]
    )
    punishments[chat_id][id_]["reasons"].append(reason)
    return punishments[chat_id][id_]["punishment"]


def InstantiateFloodDictionary(chat_id: int, user_id: int):
    # if chat_id not registered into the flood dictionary register it
    if chat_id not in flood:
        flood[chat_id] = {}
    if user_id not in flood[chat_id]:
        flood[chat_id][user_id] = {}

        flood[chat_id][user_id]["cb_qrs_times"] = []
        flood[chat_id][user_id]["cb_qrs_flood_wait_expiry_date"] = 0
        # from 0 to X minutes of wait depending on how much of an idiot is the user
        flood[chat_id][user_id]["cb_qrs_previous_flood_wait"] = 0
        # no warned parameter for callback_queries because they have no limit, just one per query and that's all

        flood[chat_id][user_id]["msgs_times"] = []


def InstantiateMsgsHashesDictionary(chat_id: int, msg_hash: str):
    # if chat_id not registered into the msgsHashes dictionary register it
    if chat_id not in msgsHashes:
        msgsHashes[chat_id] = {}
    if msg_hash not in msgsHashes[chat_id]:
        msgsHashes[chat_id][msg_hash] = []


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.new_chat_members, group=-10,
)
def RemoveKickedPeople(client: pyrogram.Client, msg: pyrogram.Message):
    # remove user from this list if (s)he/they has/have already been kicked^ in this chat
    for user in msg.new_chat_members:
        if msg.chat.id in utils.tmp_dicts["kickedPeople"]:
            if user.id in utils.tmp_dicts["kickedPeople"][msg.chat.id]:
                utils.tmp_dicts["kickedPeople"][msg.chat.id].remove(user.id)


# @pyrogram.Client.on_message(pyrogram.Filters.linked_channel, group=-9) # TODO uncomment this line and remove check inside pre_process_post.py
def MessageFromConnectedChannel(client: pyrogram.Client, msg: pyrogram.Message):
    msg.stop_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.channel, group=-9)
def MessageFromChannel(client: pyrogram.Client, msg: pyrogram.Message):
    msg.stop_propagation()


@pyrogram.Client.on_callback_query(my_filters.callback_channel, group=-9)
def CallbackQueryFromChannel(client: pyrogram.Client, cb_qry: pyrogram.CallbackQuery):
    cb_qry.stop_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.text | pyrogram.Filters.caption, group=-9,
)
def CheckMessageStartingWithBotUsername(client: pyrogram.Client, msg: pyrogram.Message):
    text_to_use = ""
    if msg.text:
        text_to_use = msg.text
    if msg.caption:
        text_to_use = msg.caption
    if text_to_use.lower().startswith(f"@{client.ME.username.lower()} "):
        if msg.text:
            msg.text = text_to_use[len(client.ME.username.lower()) + 2 :]
        if msg.caption:
            msg.caption = text_to_use[len(client.ME.username.lower()) + 2 :]
    msg.continue_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.migrate_from_chat_id, group=-9)
def MigrationFromGroup(client: pyrogram.Client, msg: pyrogram.Message):
    # managing migration to supergroup so ignore
    msg.stop_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.migrate_to_chat_id, group=-9)
def MigrationToSupergroup(client: pyrogram.Client, msg: pyrogram.Message):
    utils.Log(
        client=client,
        chat_id=msg.chat.id,
        executer=msg.from_user.id,
        action=f"MIGRATING TO {msg.migrate_to_chat_id}",
        target=msg.chat.id,
        chat_settings=msg.chat.settings,
    )
    migrating_chat: db_management.Chats = db_management.Chats.get_or_none(
        id=msg.chat.id
    )
    migrating_chat.id = msg.migrate_to_chat_id
    migrating_chat.save()
    utils.Log(
        client=client,
        chat_id=msg.migrate_to_chat_id,
        executer=msg.from_user.id,
        action=f"MIGRATION COMPLETED. MIGRATED FROM {msg.chat.id}",
        target=msg.migrate_to_chat_id,
        chat_settings=msg.chat.settings,
    )
    msg.stop_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.private, group=-9)
def CheckPrivateMessage(client: pyrogram.Client, msg: pyrogram.Message):
    InstantiatePunishmentDictionary(chat_id=msg.chat.id, id_=msg.message_id)

    # if user is blocked don't process
    if msg.chat.settings.block_expiration > datetime.datetime.utcnow():
        print(f"BLOCKED USER {msg.chat.id}")
        if msg.message_id in punishments[msg.chat.id]:
            punishments[msg.chat.id].pop(msg.message_id)
        msg.stop_propagation()
    # if user is master skip checks
    if utils.IsMaster(user_id=msg.from_user.id):
        if msg.message_id in punishments[msg.chat.id]:
            punishments[msg.chat.id].pop(msg.message_id)
        return

    # flood
    if not msg.edit_date:
        InstantiateFloodDictionary(chat_id=msg.chat.id, user_id=msg.from_user.id)

        # append last message
        flood[msg.chat.id][msg.from_user.id]["msgs_times"].append(msg.date)
        # remove all messages older than X seconds from the current message
        flood[msg.chat.id][msg.from_user.id]["msgs_times"] = [
            x
            for x in flood[msg.chat.id][msg.from_user.id]["msgs_times"]
            if msg.date - x <= utils.config["settings"]["max_flood_msgs_time"]
        ]

        # check if X+ messages in less than Y seconds from the current message
        if (
            len(flood[msg.chat.id][msg.from_user.id]["msgs_times"])
            >= utils.config["settings"]["max_flood_msgs_user"]
        ):
            print(f"MESSAGE FLOODER {msg.from_user.id} IN {msg.chat.id}")
            msg.from_user.settings.private_flood_counter += 1
            msg.from_user.settings.save()
            flood_wait = 120
            # is the user flooding inside X seconds window after the previous expiry date?
            if (
                msg.date
                <= msg.from_user.settings.block_expiration.replace(
                    tzinfo=datetime.timezone.utc
                ).timestamp()
                + utils.config["settings"]["flood_surveillance_window"]
            ):
                # double previous flood wait time because it's a repeat flooder
                print("REPEAT FLOODER")
                flood_wait = (
                    msg.from_user.settings.block_expiration
                    - msg.from_user.settings.block_datetime
                ).total_seconds() * 2
            text = methods.Block(
                client=client,
                executer=client.ME.id,
                target=msg.from_user.id,
                chat_id=msg.chat.id,
                seconds=flood_wait,
                reasons=_(msg.from_user.settings.language, "reason_private_flood"),
                chat_settings=msg.chat.settings,
            )
            if text:
                methods.ReplyText(client=client, msg=msg, text=text)
            # do not process messages for flooders
            if msg.message_id in punishments[msg.chat.id]:
                punishments[msg.chat.id].pop(msg.message_id)
            msg.stop_propagation()
    # if the message has been edited more than 8 seconds ago stop
    if msg.edit_date and msg.edit_date - msg.date > 8:
        msg.stop_propagation()
    # if the message is not edited and has been sent more than 15 seconds ago stop
    if not msg.edit_date and time.time() - msg.date > 15:
        msg.stop_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.group, group=-9)
def InitGroupMessage(client: pyrogram.Client, msg: pyrogram.Message):
    InstantiatePunishmentDictionary(chat_id=msg.chat.id, id_=msg.message_id)
    utils.InstantiateKickedPeopleDictionary(chat_id=msg.chat.id)

    # if chat is banned don't process
    if msg.chat.settings.is_banned:
        if msg.message_id in punishments[msg.chat.id]:
            punishments[msg.chat.id].pop(msg.message_id)
        msg.stop_propagation()
    # if bot not enabled and user is not owner^ don't process
    if not (
        msg.chat.settings.is_bot_on
        or utils.IsOwnerOrHigher(
            user_id=msg.from_user.id, chat_id=msg.chat.id, r_user_chat=msg.r_user_chat
        )
    ):
        if msg.message_id in punishments[msg.chat.id]:
            punishments[msg.chat.id].pop(msg.message_id)
        msg.stop_propagation()

    # if user is juniormod^ or whitelisted skip checks
    if (
        utils.IsJuniorModOrHigher(
            user_id=msg.from_user.id, chat_id=msg.chat.id, r_user_chat=msg.r_user_chat
        )
        or msg.r_user_chat.is_whitelisted
    ):
        if msg.message_id in punishments[msg.chat.id]:
            punishments[msg.chat.id].pop(msg.message_id)
        return

    # pre action
    pre_action: db_management.ChatPreActionList = db_management.ChatPreActionList.get_or_none(
        chat_id=msg.chat.id, user_id=msg.from_user.id
    )
    if pre_action:
        punishment = 0
        if pre_action.action == "prerestrict":
            punishment = 5
        elif pre_action.action == "preban":
            punishment = 7
        success = methods.AutoPunish(
            client=client,
            executer=client.ME.id,
            target=msg.from_user.id,
            chat_id=msg.chat.id,
            punishment=punishment,
            reasons="pre_action",
            auto_group_notice=True,
        )
        if msg.message_id in punishments[msg.chat.id]:
            punishments[msg.chat.id].pop(msg.message_id)
        if success:
            pre_action.delete_instance()
        msg.stop_propagation()
    # flood
    if msg.chat.settings.flood_punishment and not msg.edit_date:
        InstantiateFloodDictionary(chat_id=msg.chat.id, user_id=msg.from_user.id)

        process_flood = True
        if msg.media_group_id:
            if msg.chat.settings.allow_media_group:
                process_flood = False

        if process_flood:
            # append last message
            flood[msg.chat.id][msg.from_user.id]["msgs_times"].append(msg.date)
            # remove all messages older than X seconds from the current message
            flood[msg.chat.id][msg.from_user.id]["msgs_times"] = [
                x
                for x in flood[msg.chat.id][msg.from_user.id]["msgs_times"]
                if msg.date - x <= msg.chat.settings.max_flood_time
            ]

            # check if X+ messages in less than Y seconds
            if (
                len(flood[msg.chat.id][msg.from_user.id]["msgs_times"])
                >= msg.chat.settings.max_flood
            ):
                print(f"MESSAGES FLOODER {msg.from_user.id} IN {msg.chat.id}")
                ChangePunishmentAddReason(
                    chat_id=msg.chat.id,
                    id_=msg.message_id,
                    punishment=msg.chat.settings.flood_punishment,
                    reason="flood",
                )
    # global ban
    if (
        msg.chat.settings.globally_banned_punishment
        and msg.from_user.settings.global_ban_expiration > datetime.date.today()
        and not msg.r_user_chat.is_global_ban_whitelisted
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.globally_banned_punishment,
            reason="globally_banned",
        )
    # anti everything
    if msg.chat.settings.anti_everything:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_everything,
            reason="everything",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.group & pyrogram.Filters.bot, group=-9)
def CheckGroupMessageFromBot(client: pyrogram.Client, msg: pyrogram.Message):
    # is bot?
    if msg.chat.settings.bot_punishment and msg.from_user.is_bot:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.bot_punishment,
            reason="bot",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.forwarded, group=-9,
)
def CheckGroupMessageForwardFromChat(client: pyrogram.Client, msg: pyrogram.Message):
    # forward from chat
    if msg.chat.settings.forward_punishment and msg.forward_from_chat:
        if not db_management.ChatWhitelistedChats.get_or_none(
            chat_id=msg.chat.id, linked_chat_id=msg.forward_from_chat.id
        ):
            ChangePunishmentAddReason(
                chat_id=msg.chat.id,
                id_=msg.message_id,
                punishment=msg.chat.settings.forward_punishment,
                reason="forward_from_channel",
            )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & (pyrogram.Filters.text | pyrogram.Filters.caption),
    group=-9,
)
def CheckGroupMessageTextCaptionName(client: pyrogram.Client, msg: pyrogram.Message):
    # CHECKS THAT REQUIRE TEXT
    text_to_use = ""
    if msg.text:
        text_to_use += f" {msg.text}"
    if msg.caption:
        text_to_use += f" {msg.caption}"
    text_to_use = text_to_use.strip()
    # anti shitstorm (text)
    if msg.chat.settings.shitstorm_punishment:
        hashing_sha512 = hashlib.sha512()
        hashing_sha512.update(text_to_use.encode("utf-8"))
        msg_hash = hashing_sha512.hexdigest()
        InstantiateMsgsHashesDictionary(chat_id=msg.chat.id, msg_hash=msg_hash)
        # append last message
        msgsHashes[msg.chat.id][msg_hash].append(msg.date)
        # remove all messages with this hash in this chat older than X seconds from the current message
        msgsHashes[msg.chat.id][msg_hash] = [
            x
            for x in msgsHashes[msg.chat.id][msg_hash]
            if msg.date - x <= utils.config["settings"]["temp_variables_expiration"]
        ]
        if len(msgsHashes[msg.chat.id][msg_hash]) > 10:
            ChangePunishmentAddReason(
                chat_id=msg.chat.id,
                id_=msg.message_id,
                punishment=msg.chat.settings.shitstorm_punishment,
                reason="text_shitstorm",
            )
            msg.from_user.settings.shitstorm_counter += 1
            msg.from_user.settings.save()
            # if shitstormer for 3+ times gban for X days where X is the number of shitstorms
            if msg.from_user.settings.shitstorm_counter > 2:
                text = methods.GBan(
                    client=client,
                    executer=client.ME.id,
                    target=msg.from_user.id,
                    chat_id=msg.chat.id,
                    seconds=msg.from_user.settings.shitstorm_counter * 86400,
                    reasons=_(msg.chat.settings.language, "reason_text_shitstorm"),
                    chat_settings=msg.chat.settings,
                    target_settings=msg.from_user.settings,
                )
                if text:
                    methods.ReplyText(client=client, msg=msg, text=text)
    # rtl
    if msg.chat.settings.rtl_punishment and (
        utils.RTL_CHARACTER in text_to_use
        or utils.RTL_CHARACTER in msg.from_user.first_name
        or (msg.from_user.last_name and utils.RTL_CHARACTER in msg.from_user.last_name)
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.rtl_punishment,
            reason="rtl_character",
        )
    # spam
    if msg.chat.settings.text_spam_punishment and (
        len(text_to_use) > 2048
        or len(msg.from_user.first_name)
        + (len(msg.from_user.last_name) if msg.from_user.last_name else 0)
        > 70
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.text_spam_punishment,
            reason="spam_long_text",
        )
    # arabic
    if msg.chat.settings.arabic_punishment and (
        utils.ARABIC_REGEX.findall(string=text_to_use)
        or utils.ARABIC_REGEX.findall(string=msg.from_user.first_name)
        or (
            msg.from_user.last_name
            and utils.ARABIC_REGEX.findall(string=msg.from_user.last_name)
        )
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.arabic_punishment,
            reason="arabic",
        )
    # censorships
    if msg.chat.settings.censorships_punishment:
        censorships: peewee.ModelSelect = msg.chat.settings.censorships
        for element in censorships:
            if not element.is_media:
                found = False
                if element.is_regex:
                    regex_check_item = re.compile(element.value, re.I)
                    found = regex_check_item.search(text_to_use)
                else:
                    found = element.value.lower() in text_to_use.lower()
                if not found:
                    if msg.reply_markup and hasattr(
                        msg.reply_markup, "inline_keyboard"
                    ):
                        for row in msg.reply_markup.inline_keyboard:
                            for button in row:
                                if element.is_regex:
                                    regex_check_item = re.compile(element.value, re.I)
                                    found = (
                                        hasattr(button, "url")
                                        and regex_check_item.match(button.url)
                                    ) or (
                                        hasattr(button, "text")
                                        and regex_check_item.search(button.text)
                                    )
                                else:
                                    found = (
                                        hasattr(button, "url")
                                        and element.value.lower() in button.url.lower()
                                    ) or (
                                        hasattr(button, "text")
                                        and element.value.lower() in button.text.lower()
                                    )
                                if found:
                                    break
                            if found:
                                break
                if found:
                    ChangePunishmentAddReason(
                        chat_id=msg.chat.id,
                        id_=msg.message_id,
                        punishment=msg.chat.settings.censorships_punishment,
                        reason="censored_text",
                    )
                    break
    # links and public usernames
    if msg.chat.settings.link_spam_punishment:
        entities_to_use: typing.List[pyrogram.MessageEntity] = []
        if msg.caption_entities:
            entities_to_use = msg.caption_entities
        elif msg.entities:
            entities_to_use = msg.entities
        # entities (text)
        for entity in entities_to_use:
            tmp = ""
            if entity.type == "mention":
                # @username
                tmp = text_to_use[entity.offset : entity.offset + entity.length]
            elif entity.type == "url":
                tmp = str(
                    utils.CleanLink(
                        url=text_to_use[entity.offset : entity.offset + entity.length]
                    )
                )
                if "t.me/joinchat" not in tmp.lower():
                    # t.me/username
                    tmp = utils.CleanUsername(username=tmp).lower()
            elif entity.type == "text_link":
                tmp = str(utils.CleanLink(url=entity.url))
                if "t.me/joinchat" not in tmp.lower():
                    # t.me/username
                    tmp = utils.CleanUsername(username=tmp).lower()
            if utils.LINK_REGEX.findall(string=tmp):
                link_parameters = (None, None, None)
                try:
                    link_parameters = utils.ResolveInviteLink(link=tmp)
                except Exception as ex:
                    print(ex)
                    traceback.print_exc()
                whitelisted_link = False
                # whitelisted link if the chat_id is equal to the id from the link
                whitelisted_link = link_parameters[1] == int(
                    str(msg.chat.id).replace("-100", "").replace("-", "")
                )
                for item in msg.chat.settings.whitelisted_chats:
                    # whitelisted link if the whitelisted_chat_id is equal to the id from the link
                    if link_parameters[1] == int(
                        str(item.whitelisted_chat_id)
                        .replace("-100", "")
                        .replace("-", "")
                    ):
                        whitelisted_link = True

                if not whitelisted_link:
                    ChangePunishmentAddReason(
                        chat_id=msg.chat.id,
                        id_=msg.message_id,
                        punishment=msg.chat.settings.link_spam_punishment,
                        reason="link_spam",
                    )
            elif utils.USERNAME_REGEX.findall(string=tmp):
                query: peewee.ModelSelect = db_management.ResolvedObjects.select().where(
                    db_management.ResolvedObjects.username == tmp[1:].lower()
                ).order_by(
                    db_management.ResolvedObjects.timestamp.desc()
                )
                resolved_obj = None
                try:
                    resolved_obj = query.get()
                except db_management.ResolvedObjects.DoesNotExist:
                    try:
                        resolved_obj = client.get_chat(
                            chat_id=utils.CleanUsername(username=tmp)
                        )
                        resolved_obj = db_management.DBObject(
                            obj=resolved_obj, client=client
                        )
                    except Exception as ex:
                        print(ex)
                        traceback.print_exc()
                if resolved_obj and (
                    resolved_obj.type == "supergroup" or resolved_obj.type == "channel"
                ):
                    whitelisted_username = False
                    # whitelisted username if the chat_id is equal to the id of the resolved_obj
                    whitelisted_username = resolved_obj.id == msg.chat.id
                    for item in msg.chat.settings.whitelisted_chats:
                        # whitelisted username if the whitelisted_chat_id is equal to the id of the resolved_obj
                        if int(
                            str(resolved_obj.id).replace("-100", "").replace("-", "")
                        ) == int(
                            str(item.whitelisted_chat_id)
                            .replace("-100", "")
                            .replace("-", "")
                        ):
                            whitelisted_username = True

                    if not whitelisted_username:
                        ChangePunishmentAddReason(
                            chat_id=msg.chat.id,
                            id_=msg.message_id,
                            punishment=msg.chat.settings.link_spam_punishment,
                            reason="public_chat_username",
                        )
        # reply_markup (buttons)
        if msg.reply_markup and hasattr(msg.reply_markup, "inline_keyboard"):
            for row in msg.reply_markup.inline_keyboard:
                for button in row:
                    if hasattr(button, "url"):
                        tmp = str(utils.CleanLink(button.url))
                        if "t.me/joinchat" not in tmp.lower():
                            # t.me/username
                            tmp = utils.CleanUsername(username=tmp).lower()
                        if utils.LINK_REGEX.findall(string=tmp):
                            link_parameters = (None, None, None)
                            try:
                                link_parameters = utils.ResolveInviteLink(link=tmp)
                            except Exception as ex:
                                print(ex)
                                traceback.print_exc()
                            whitelisted_link = False
                            # whitelisted link if the chat_id is equal to the id from the link
                            whitelisted_link = link_parameters[1] == int(
                                str(msg.chat.id).replace("-100", "").replace("-", "")
                            )
                            for item in msg.chat.settings.whitelisted_chats:
                                # whitelisted link if the whitelisted_chat_id is equal to the id from the link
                                if link_parameters[1] == int(
                                    str(item.whitelisted_chat_id)
                                    .replace("-100", "")
                                    .replace("-", "")
                                ):
                                    whitelisted_link = True

                            if not whitelisted_link:
                                ChangePunishmentAddReason(
                                    chat_id=msg.chat.id,
                                    id_=msg.message_id,
                                    punishment=msg.chat.settings.link_spam_punishment,
                                    reason="link_spam",
                                )
                        elif utils.USERNAME_REGEX.findall(string=tmp):
                            query: peewee.ModelSelect = db_management.ResolvedObjects.select().where(
                                db_management.ResolvedObjects.username
                                == tmp[1:].lower()
                            ).order_by(
                                db_management.ResolvedObjects.timestamp.desc()
                            )
                            try:
                                resolved_obj = query.get()
                            except db_management.ResolvedObjects.DoesNotExist:
                                try:
                                    resolved_obj = client.get_chat(
                                        chat_id=utils.CleanUsername(username=tmp)
                                    )
                                    resolved_obj = db_management.DBObject(
                                        obj=resolved_obj, client=client
                                    )
                                except Exception as ex:
                                    print(ex)
                                    traceback.print_exc()
                            if resolved_obj and (
                                resolved_obj.type == "supergroup"
                                or resolved_obj.type == "channel"
                            ):
                                whitelisted_username = False
                                # whitelisted username if the chat_id is equal to the id from the resolved_obj
                                whitelisted_username = resolved_obj.id == msg.chat.id
                                for item in msg.chat.settings.whitelisted_chats:
                                    # whitelisted username if the whitelisted_chat_id is equal to the id from the resolved_obj
                                    if int(
                                        str(resolved_obj.id)
                                        .replace("-100", "")
                                        .replace("-", "")
                                    ) == int(
                                        str(item.whitelisted_chat_id)
                                        .replace("-100", "")
                                        .replace("-", "")
                                    ):
                                        whitelisted_username = True

                                if not whitelisted_username:
                                    ChangePunishmentAddReason(
                                        chat_id=msg.chat.id,
                                        id_=msg.message_id,
                                        punishment=msg.chat.settings.link_spam_punishment,
                                        reason="public_chat_username",
                                    )
    # anti text
    if msg.chat.settings.anti_text:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_text,
            reason="text",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.media, group=-9,
)
def InitCheckGroupMessageMedia(client: pyrogram.Client, msg: pyrogram.Message):
    # CHECKS THAT REQUIRE MEDIA
    # anti shitstorm (media)
    if msg.chat.settings.shitstorm_punishment:
        media, type_ = utils.ExtractMedia(msg=msg)
        print(media.media_id)
        InstantiateMsgsHashesDictionary(chat_id=msg.chat.id, msg_hash=media.media_id)
        # append last message
        msgsHashes[msg.chat.id][media.media_id].append(msg.date)
        # remove all messages with this hash in this chat older than X seconds from the current message
        msgsHashes[msg.chat.id][media.media_id] = [
            x
            for x in msgsHashes[msg.chat.id][media.media_id]
            if msg.date - x <= utils.config["settings"]["temp_variables_expiration"]
        ]
        if len(msgsHashes[msg.chat.id][media.media_id]) > 10:
            ChangePunishmentAddReason(
                chat_id=msg.chat.id,
                id_=msg.message_id,
                punishment=msg.chat.settings.shitstorm_punishment,
                reason="media_shitstorm",
            )
            msg.from_user.settings.shitstorm_counter += 1
            msg.from_user.settings.save()
            # if shitstormer for 3+ times gban for X days where X is the number of shitstorms
            if msg.from_user.settings.shitstorm_counter > 2:
                text = methods.GBan(
                    client=client,
                    executer=client.ME.id,
                    target=msg.from_user.id,
                    chat_id=msg.chat.id,
                    seconds=msg.from_user.settings.shitstorm_counter * 86400,
                    reasons=_(msg.chat.settings.language, "reason_media_shitstorm"),
                    chat_settings=msg.chat.settings,
                    target_settings=msg.from_user.settings,
                )
                if text:
                    methods.ReplyText(client=client, msg=msg, text=text)
    # censorships
    if msg.chat.settings.censorships_punishment:
        censorships: peewee.ModelSelect = msg.chat.settings.censorships
        for element in censorships:
            if element.is_media:
                media, type_ = utils.ExtractMedia(msg=msg)
                if media and media.media_id.lower() == element.value.lower():
                    ChangePunishmentAddReason(
                        chat_id=msg.chat.id,
                        id_=msg.message_id,
                        punishment=msg.chat.settings.censorships_punishment,
                        reason="censored_media",
                    )
                    break
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.animation, group=-9,
)
def CheckGroupAnimation(client: pyrogram.Client, msg: pyrogram.Message):
    # anti animation
    if msg.chat.settings.anti_animation or utils.IsInNightMode(
        chat_settings=msg.chat.settings
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_animation
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else max(
                msg.chat.settings.anti_animation,
                msg.chat.settings.night_mode_punishment,
            ),
            reason="animation"
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else "night_mode",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.audio, group=-9,
)
def CheckGroupAudio(client: pyrogram.Client, msg: pyrogram.Message):
    # anti audio
    if msg.chat.settings.anti_audio:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_audio,
            reason="audio",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.contact, group=-9,
)
def CheckGroupContact(client: pyrogram.Client, msg: pyrogram.Message):
    # anti contact
    if msg.chat.settings.anti_contact:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_contact,
            reason="contact",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.document, group=-9,
)
def CheckGroupDocument(client: pyrogram.Client, msg: pyrogram.Message):
    # anti document
    if msg.chat.settings.anti_document:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_document,
            reason="document",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & (pyrogram.Filters.game | pyrogram.Filters.game_high_score),
    group=-9,
)
def CheckGroupGame(client: pyrogram.Client, msg: pyrogram.Message):
    # anti game
    if msg.chat.settings.anti_game:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_game,
            reason="game",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.location, group=-9,
)
def CheckGroupLocation(client: pyrogram.Client, msg: pyrogram.Message):
    # anti location
    if msg.chat.settings.anti_location:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_location,
            reason="location",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.photo, group=-9,
)
def CheckGroupPhoto(client: pyrogram.Client, msg: pyrogram.Message):
    # anti photo
    if msg.chat.settings.anti_photo or utils.IsInNightMode(
        chat_settings=msg.chat.settings
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_photo
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else max(
                msg.chat.settings.anti_photo, msg.chat.settings.night_mode_punishment,
            ),
            reason="photo"
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else "night_mode",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.group & pyrogram.Filters.poll, group=-9)
def CheckGroupPoll(client: pyrogram.Client, msg: pyrogram.Message):
    # anti poll
    if msg.chat.settings.anti_poll:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_poll,
            reason="poll",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.sticker, group=-9,
)
def CheckGroupSticker(client: pyrogram.Client, msg: pyrogram.Message):
    # anti sticker
    if msg.chat.settings.anti_sticker or utils.IsInNightMode(
        chat_settings=msg.chat.settings
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_sticker
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else max(
                msg.chat.settings.anti_sticker, msg.chat.settings.night_mode_punishment,
            ),
            reason="sticker"
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else "night_mode",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.venue, group=-9,
)
def CheckGroupVenue(client: pyrogram.Client, msg: pyrogram.Message):
    # anti location
    if msg.chat.settings.anti_venue:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_venue,
            reason="venue",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.video, group=-9,
)
def CheckGroupVideo(client: pyrogram.Client, msg: pyrogram.Message):
    # anti video
    if msg.chat.settings.anti_video or utils.IsInNightMode(
        chat_settings=msg.chat.settings
    ):
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_video
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else max(
                msg.chat.settings.anti_video, msg.chat.settings.night_mode_punishment,
            ),
            reason="video"
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else "night_mode",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.video_note, group=-9,
)
def CheckGroupVideoNote(client: pyrogram.Client, msg: pyrogram.Message):
    # anti video_note
    if msg.chat.settings.anti_video_note:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_video_note,
            reason="video_note",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.voice, group=-9,
)
def CheckGroupVoice(client: pyrogram.Client, msg: pyrogram.Message):
    # anti voice
    if msg.chat.settings.anti_voice:
        ChangePunishmentAddReason(
            chat_id=msg.chat.id,
            id_=msg.message_id,
            punishment=msg.chat.settings.anti_voice,
            reason="voice",
        )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.new_chat_members, group=-9,
)
def CheckGroupMessageAdder(client: pyrogram.Client, msg: pyrogram.Message):
    # if user didn't add (him/her)self (didn't join via invite link)
    if msg.from_user.id != msg.new_chat_members[0].id:
        # add users/bots
        if msg.chat.settings.add_punishment or utils.IsInNightMode(
            chat_settings=msg.chat.settings
        ):
            ChangePunishmentAddReason(
                chat_id=msg.chat.id,
                id_=msg.message_id,
                punishment=msg.chat.settings.add_punishment
                if not utils.IsInNightMode(chat_settings=msg.chat.settings)
                else max(
                    msg.chat.settings.add_punishment,
                    msg.chat.settings.night_mode_punishment,
                ),
                reason="add_user"
                if not utils.IsInNightMode(chat_settings=msg.chat.settings)
                else "night_mode",
            )
        # invitation flood
        max_invites = (
            msg.chat.settings.max_invites
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else 1
        )
        if len(msg.new_chat_members) > max_invites:
            ChangePunishmentAddReason(
                chat_id=msg.chat.id,
                id_=msg.message_id,
                punishment=7,
                reason="invitation_flood"
                if not utils.IsInNightMode(chat_settings=msg.chat.settings)
                else "night_mode",
            )
    else:
        # join
        if msg.chat.settings.join_punishment:
            ChangePunishmentAddReason(
                chat_id=msg.chat.id,
                id_=msg.message_id,
                punishment=msg.chat.settings.join_punishment,
                reason="join",
            )
    msg.continue_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.group, group=-9)
def CheckGroupMessagePunish(client: pyrogram.Client, msg: pyrogram.Message):
    if punishments[msg.chat.id][msg.message_id]["punishment"]:
        # punish user
        if punishments[msg.chat.id][msg.message_id]["punishment"] > 1:
            # if user will be punished with warn^ forecast new warns value and check if (s)he will reach max_warns
            if (
                msg.chat.settings.max_warns_punishment
                and msg.r_user_chat.warns + 1 >= msg.chat.settings.max_warns
            ):
                # add max_warns to punishments
                ChangePunishmentAddReason(
                    chat_id=msg.chat.id,
                    id_=msg.message_id,
                    punishment=msg.chat.settings.max_warns_punishment,
                    reason="max_warns_reached",
                )
        methods.AutoPunish(
            client=client,
            executer=client.ME.id,
            target=msg.from_user.id,
            chat_id=msg.chat.id,
            punishment=punishments[msg.chat.id][msg.message_id]["punishment"],
            reasons=punishments[msg.chat.id][msg.message_id]["reasons"],
            message_ids=msg.message_id,
            auto_group_notice=True,
        )
    else:
        # check if user has reached max_warns
        if (
            msg.chat.settings.max_warns_punishment
            and msg.r_user_chat.warns >= msg.chat.settings.max_warns
        ):
            # punish user
            methods.AutoPunish(
                client=client,
                executer=client.ME.id,
                target=msg.from_user.id,
                chat_id=msg.chat.id,
                punishment=msg.chat.settings.max_warns_punishment,
                reasons="max_warns_reached",
                auto_group_notice=True,
            )
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group & pyrogram.Filters.new_chat_members, group=-9,
)
def CheckGroupMessageAdded(client: pyrogram.Client, msg: pyrogram.Message):
    text = ""
    if msg.from_user.id != msg.new_chat_members[0].id:
        # user added someone else
        # check added people
        highest_added_punishment = 0
        max_invites = (
            msg.chat.settings.max_invites
            if not utils.IsInNightMode(chat_settings=msg.chat.settings)
            else 1
        )
        for user in msg.new_chat_members:
            added_settings: db_management.UserSettings = db_management.UserSettings.get(
                user_id=user.id
            )
            R_added_chat: db_management.RUserChat = db_management.RUserChat.get(
                user_id=user.id, chat_id=msg.chat.id
            )
            # if user is juniormod^ or whitelisted skip checks
            if (
                utils.IsJuniorModOrHigher(
                    user_id=msg.from_user.id,
                    chat_id=msg.chat.id,
                    r_user_chat=R_added_chat,
                )
                or R_added_chat.is_whitelisted
            ):
                continue

            # add users/bots
            if msg.chat.settings.add_punishment or utils.IsInNightMode(
                chat_settings=msg.chat.settings
            ):
                res = methods.AutoPunish(
                    client=client,
                    executer=client.ME.id,
                    target=user.id,
                    chat_id=msg.chat.id,
                    punishment=7,
                    reasons="invited"
                    if not utils.IsInNightMode(chat_settings=msg.chat.settings)
                    else "night_mode",
                    auto_group_notice=False,
                )
                if res:
                    text += (
                        f"{res}\n"
                        if msg.chat.settings.group_notices
                        and user.id not in utils.tmp_dicts["kickedPeople"][msg.chat.id]
                        else ""
                    )
                    utils.tmp_dicts["kickedPeople"][msg.chat.id].add(user.id)
                continue

            # flood invited
            if len(msg.new_chat_members) > max_invites:
                res = methods.AutoPunish(
                    client=client,
                    executer=client.ME.id,
                    target=user.id,
                    chat_id=msg.chat.id,
                    punishment=7,
                    reasons="flood_invited"
                    if not utils.IsInNightMode(chat_settings=msg.chat.settings)
                    else "night_mode",
                    auto_group_notice=False,
                )
                if res:
                    text += (
                        f"{res}\n"
                        if msg.chat.settings.group_notices
                        and user.id not in utils.tmp_dicts["kickedPeople"][msg.chat.id]
                        else ""
                    )
                    utils.tmp_dicts["kickedPeople"][msg.chat.id].add(user.id)
                continue
            # pre action
            pre_action: db_management.ChatPreActionList = db_management.ChatPreActionList.get_or_none(
                chat_id=msg.chat.id, user_id=user.id
            )
            if pre_action:
                punishment = 0
                if pre_action.action == "prerestrict":
                    punishment = 5
                elif pre_action.action == "preban":
                    punishment = 7
                res = methods.AutoPunish(
                    client=client,
                    executer=client.ME.id,
                    target=user.id,
                    chat_id=msg.chat.id,
                    punishment=punishment,
                    reasons="pre_action",
                    auto_group_notice=False,
                )
                if res:
                    text += (
                        f"{res}\n"
                        if msg.chat.settings.group_notices
                        and msg.chat.settings.group_notices <= punishment
                        and user.id not in utils.tmp_dicts["kickedPeople"][msg.chat.id]
                        else ""
                    )
                    pre_action.delete_instance()
                    utils.tmp_dicts["kickedPeople"][msg.chat.id].add(user.id)
                continue

            tmp_highest_added_punishment = 0
            reasons = []
            # arabic
            if (
                msg.chat.settings.arabic_punishment
                and utils.ARABIC_REGEX.findall(string=user.first_name)
                or (
                    user.last_name and utils.ARABIC_REGEX.findall(string=user.last_name)
                )
            ):
                tmp_highest_added_punishment = max(
                    msg.chat.settings.arabic_punishment, tmp_highest_added_punishment
                )
                reasons.append("arabic_name")
            # bot
            if msg.chat.settings.bot_punishment and user.is_bot:
                tmp_highest_added_punishment = max(
                    msg.chat.settings.bot_punishment, tmp_highest_added_punishment
                )
                reasons.append("bot")
            # global ban
            if (
                msg.chat.settings.globally_banned_punishment
                and added_settings.global_ban_expiration > datetime.date.today()
                and not R_added_chat.is_global_ban_whitelisted
            ):
                tmp_highest_added_punishment = max(
                    msg.chat.settings.globally_banned_punishment,
                    tmp_highest_added_punishment,
                )
                reasons.append("globally_banned")
            # rtl
            if (
                msg.chat.settings.rtl_punishment
                and utils.RTL_CHARACTER in user.first_name
                or (user.last_name and utils.RTL_CHARACTER in user.last_name)
            ):
                tmp_highest_added_punishment = max(
                    msg.chat.settings.rtl_punishment, tmp_highest_added_punishment
                )
                reasons.append("rtl_name")
            # spam
            if (
                msg.chat.settings.text_spam_punishment
                and len(user.first_name)
                + (len(user.last_name) if user.last_name else 0)
                > 70
            ):
                tmp_highest_added_punishment = max(
                    msg.chat.settings.text_spam_punishment, tmp_highest_added_punishment
                )
                reasons.append("spam_name")

            if tmp_highest_added_punishment:
                # punish user
                highest_added_punishment = max(
                    highest_added_punishment, tmp_highest_added_punishment
                )
                if tmp_highest_added_punishment > 1:
                    # if user will be punished with warn^ forecast new warns value and check if (s)he will reach max_warns
                    if (
                        msg.chat.settings.max_warns_punishment
                        and R_added_chat.warns + 1 >= msg.chat.settings.max_warns
                    ):
                        # add max_warns to punishments
                        tmp_highest_added_punishment = max(
                            msg.chat.settings.max_warns_punishment,
                            tmp_highest_added_punishment,
                        )
                        reasons.append("max_warns_reached")
                    res = methods.AutoPunish(
                        client=client,
                        executer=client.ME.id,
                        target=user.id,
                        chat_id=msg.chat.id,
                        punishment=tmp_highest_added_punishment,
                        reasons=reasons,
                        auto_group_notice=False,
                    )
                    if res:
                        text += (
                            f"{res}\n"
                            if msg.chat.settings.group_notices
                            and msg.chat.settings.group_notices
                            <= tmp_highest_added_punishment
                            and user.id
                            not in utils.tmp_dicts["kickedPeople"][msg.chat.id]
                            else ""
                        )
                        if tmp_highest_added_punishment > 2:
                            utils.tmp_dicts["kickedPeople"][msg.chat.id].add(user.id)
            else:
                # check if user has reached max_warns
                if (
                    msg.chat.settings.max_warns_punishment
                    and R_added_chat.warns >= msg.chat.settings.max_warns
                ):
                    # punish user
                    res = methods.AutoPunish(
                        client=client,
                        executer=client.ME.id,
                        target=user.id,
                        chat_id=msg.chat.id,
                        punishment=msg.chat.settings.max_warns_punishment,
                        reasons="max_warns_reached",
                        auto_group_notice=False,
                    )
                    if res:
                        text += (
                            f"{res}\n"
                            if msg.chat.settings.group_notices
                            and msg.chat.settings.group_notices
                            <= msg.chat.settings.max_warns_punishment
                            and user.id
                            not in utils.tmp_dicts["kickedPeople"][msg.chat.id]
                            else ""
                        )
                        utils.tmp_dicts["kickedPeople"][msg.chat.id].add(user.id)
            msg.continue_propagation()

    if text and (
        msg.chat.settings.group_notices
        and msg.chat.settings.group_notices <= highest_added_punishment
    ):
        methods.ReplyText(client=client, msg=msg, text=text)
    msg.continue_propagation()


@pyrogram.Client.on_message(pyrogram.Filters.group, group=-8)
def CheckGroupMessageTime(client: pyrogram.Client, msg: pyrogram.Message):
    # if someone has already been punished don't process
    if msg.message_id in punishments[msg.chat.id]:
        if punishments[msg.chat.id][msg.message_id]["punishment"]:
            if msg.message_id in punishments[msg.chat.id]:
                punishments[msg.chat.id].pop(msg.message_id)
            msg.stop_propagation()

        if msg.message_id in punishments[msg.chat.id]:
            punishments[msg.chat.id].pop(msg.message_id)
    # if the message has been edited more than 20 seconds ago stop
    if msg.edit_date and msg.edit_date - msg.date > 20:
        print("OLD EDITED MESSAGE")
        msg.stop_propagation()
    # if the message is not edited and has been sent more than 30 seconds ago stop
    if not msg.edit_date and time.time() - msg.date > 30:
        print("OLD MESSAGE")
        msg.stop_propagation()
    msg.continue_propagation()


@pyrogram.Client.on_callback_query(my_filters.callback_private, group=-9)
def InitPrivateCallbackQuery(client: pyrogram.Client, cb_qry: pyrogram.CallbackQuery):
    InstantiatePunishmentDictionary(chat_id=cb_qry.message.chat.id, id_=cb_qry.id)

    # if user is blocked don't process
    if cb_qry.from_user.settings.block_expiration > datetime.datetime.utcnow():
        print(f"BLOCKED USER {cb_qry.from_user.id}")
        if cb_qry.id in punishments[cb_qry.message.chat.id]:
            punishments[cb_qry.message.chat.id].pop(cb_qry.id)
        cb_qry.stop_propagation()
    # if user is master skip checks
    if utils.IsMaster(user_id=cb_qry.from_user.id):
        if cb_qry.id in punishments[cb_qry.message.chat.id]:
            punishments[cb_qry.message.chat.id].pop(cb_qry.id)

    cb_qry.continue_propagation()


@pyrogram.Client.on_callback_query(my_filters.callback_group, group=-9)
def InitGroupCallbackQuery(client: pyrogram.Client, cb_qry: pyrogram.CallbackQuery):
    InstantiatePunishmentDictionary(chat_id=cb_qry.message.chat.id, id_=cb_qry.id)
    utils.InstantiateKickedPeopleDictionary(chat_id=cb_qry.message.chat.id)

    # if chat is banned don't process
    if cb_qry.message.chat.settings.is_banned:
        if cb_qry.id in punishments[cb_qry.message.chat.id]:
            punishments[cb_qry.message.chat.id].pop(cb_qry.id)
        cb_qry.stop_propagation()
    # if bot not enabled and user is not owner^ don't process
    if not (
        cb_qry.message.chat.settings.is_bot_on
        or utils.IsOwnerOrHigher(
            user_id=cb_qry.from_user.id,
            chat_id=cb_qry.message.chat.id,
            r_user_chat=cb_qry.r_user_chat,
        )
    ):
        if cb_qry.id in punishments[cb_qry.message.chat.id]:
            punishments[cb_qry.message.chat.id].pop(cb_qry.id)
        cb_qry.stop_propagation()

    # if user is juniormod^ or whitelisted skip checks
    if (
        utils.IsJuniorModOrHigher(
            user_id=cb_qry.from_user.id,
            chat_id=cb_qry.message.chat.id,
            r_user_chat=cb_qry.r_user_chat,
        )
        or cb_qry.r_user_chat.is_whitelisted
    ):
        if cb_qry.id in punishments[cb_qry.message.chat.id]:
            punishments[cb_qry.message.chat.id].pop(cb_qry.id)
        cb_qry.continue_propagation()

    # pre action
    pre_action: db_management.ChatPreActionList = db_management.ChatPreActionList.get_or_none(
        chat_id=cb_qry.message.chat.id, user_id=cb_qry.from_user.id
    )
    if pre_action:
        punishment = 0
        if pre_action.action == "prerestrict":
            punishment = 5
        elif pre_action.action == "preban":
            punishment = 7
        success = methods.AutoPunish(
            client=client,
            executer=client.ME.id,
            target=cb_qry.from_user.id,
            chat_id=cb_qry.message.chat.id,
            punishment=punishment,
            reasons="pre_action",
            auto_group_notice=True,
        )
        if cb_qry.id in punishments[cb_qry.message.chat.id]:
            punishments[cb_qry.message.chat.id].pop(cb_qry.id)
        if success:
            pre_action.delete_instance()
        cb_qry.stop_propagation()
    # anti everything
    if cb_qry.message.chat.settings.anti_everything:
        if cb_qry.id in punishments[cb_qry.message.chat.id]:
            punishments[cb_qry.message.chat.id].pop(cb_qry.id)
        cb_qry.stop_propagation()
    # arabic
    if (
        utils.ARABIC_REGEX.findall(string=cb_qry.from_user.first_name)
        or (
            cb_qry.from_user.last_name
            and utils.ARABIC_REGEX.findall(string=cb_qry.from_user.last_name)
        )
    ) and cb_qry.message.chat.settings.arabic_punishment:
        ChangePunishmentAddReason(
            chat_id=cb_qry.message.chat.id,
            id_=cb_qry.id,
            punishment=cb_qry.message.chat.settings.arabic_punishment,
            reason="arabic_name",
        )
    # global ban
    if (
        cb_qry.from_user.settings.global_ban_expiration > datetime.date.today()
        and not cb_qry.message.r_user_chat.is_global_ban_whitelisted
        and cb_qry.message.chat.settings.globally_banned_punishment
    ):
        ChangePunishmentAddReason(
            chat_id=cb_qry.message.chat.id,
            id_=cb_qry.id,
            punishment=cb_qry.message.chat.settings.globally_banned_punishment,
            reason="globally_banned",
        )
    # rtl
    if (
        utils.RTL_CHARACTER in cb_qry.from_user.first_name
        or (
            cb_qry.from_user.last_name
            and utils.RTL_CHARACTER in cb_qry.from_user.last_name
        )
    ) and cb_qry.message.chat.settings.rtl_punishment:
        ChangePunishmentAddReason(
            chat_id=cb_qry.message.chat.id,
            id_=cb_qry.id,
            punishment=cb_qry.message.chat.settings.rtl_punishment,
            reason="rtl_name",
        )
    # spam
    if (
        len(cb_qry.from_user.first_name)
        + (len(cb_qry.from_user.last_name) if cb_qry.from_user.last_name else 0)
        > 70
    ) and cb_qry.message.chat.settings.text_spam_punishment:
        ChangePunishmentAddReason(
            chat_id=cb_qry.message.chat.id,
            id_=cb_qry.id,
            punishment=cb_qry.message.chat.settings.text_spam_punishment,
            reason="spam_name",
        )
    if punishments[cb_qry.message.chat.id][cb_qry.id]["punishment"]:
        if punishments[cb_qry.message.chat.id][cb_qry.id]["punishment"] > 1:
            # if user will be punished with warn^ forecast new warns value and check if (s)he will reach max_warns
            if (
                cb_qry.message.chat.settings.max_warns_punishment
                and cb_qry.message.r_user_chat.warns + 1
                >= cb_qry.message.chat.settings.max_warns
            ):
                # add max_warns to punishments
                ChangePunishmentAddReason(
                    chat_id=cb_qry.message.chat.id,
                    id_=cb_qry.id,
                    punishment=cb_qry.message.settings.max_warns_punishment,
                    reason="max_warns_reached",
                )
            methods.AutoPunish(
                client=client,
                executer=client.ME.id,
                target=cb_qry.from_user.id,
                chat_id=cb_qry.message.chat.id,
                punishment=punishments[cb_qry.message.chat.id][cb_qry.id]["punishment"],
                reasons=punishments[cb_qry.message.chat.id][cb_qry.id]["reasons"],
                auto_group_notice=True,
            )
    else:
        # check if user has reached max_warns
        if (
            cb_qry.message.chat.settings.max_warns_punishment
            and cb_qry.message.r_user_chat.warns
            >= cb_qry.message.chat.settings.max_warns
        ):
            methods.AutoPunish(
                client=client,
                executer=client.ME.id,
                target=cb_qry.from_user.id,
                chat_id=cb_qry.message.chat.id,
                punishment=cb_qry.message.chat.settings.max_warns_punishment,
                reasons="max_warns_reached",
                auto_group_notice=True,
            )

    cb_qry.continue_propagation()


@pyrogram.Client.on_callback_query(
    my_filters.callback_regex(r"^useless(.*)", re.I)
    & (my_filters.callback_private | my_filters.callback_group),
    group=-9,
)
def CallbackQueryUseless(client: pyrogram.Client, cb_qry: pyrogram.CallbackQuery):
    methods.CallbackQueryAnswer(
        cb_qry=cb_qry,
        text=_(cb_qry.from_user.settings.language, "useless_button"),
        show_alert=False,
    )
    cb_qry.stop_propagation()


@pyrogram.Client.on_callback_query(
    my_filters.callback_private | my_filters.callback_group, group=-9
)
def CheckFloodCallbackQuery(client: pyrogram.Client, cb_qry: pyrogram.CallbackQuery):
    # flood
    # take the current time
    timestamp_ = time.time()
    InstantiateFloodDictionary(
        chat_id=cb_qry.message.chat.id, user_id=cb_qry.from_user.id
    )
    # if this is not a callback query asking for information check flood
    if not cb_qry.data.startswith("(i)"):
        # remove all callback_queries older than X seconds from the current callback_query(recorded time)
        flood[cb_qry.message.chat.id][cb_qry.from_user.id]["cb_qrs_times"] = [
            x
            for x in flood[cb_qry.message.chat.id][cb_qry.from_user.id]["cb_qrs_times"]
            if timestamp_ - x <= utils.config["settings"]["max_flood_cb_qrs_time"]
        ]
        # if this user is inside the flood_wait time stop
        if (
            timestamp_
            < flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                "cb_qrs_flood_wait_expiry_date"
            ]
        ):
            # do not process callback_queries for flooders
            if cb_qry.id in punishments[cb_qry.message.chat.id]:
                punishments[cb_qry.message.chat.id].pop(cb_qry.id)
            text = _(
                cb_qry.from_user.settings.language, "wait_X_seconds_inline_flood",
            ).format(
                utils.TimeFormatter(
                    (
                        flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                            "cb_qrs_flood_wait_expiry_date"
                        ]
                        - timestamp_
                    )
                    * 1000
                )
            )
            # the show_alert parameter will probably slow down the user inhibiting flood
            methods.CallbackQueryAnswer(cb_qry=cb_qry, text=text, show_alert=True)
            cb_qry.stop_propagation()

        # append last callback_query(recorded time)
        flood[cb_qry.message.chat.id][cb_qry.from_user.id]["cb_qrs_times"].append(
            timestamp_
        )
        # check if X+ callback_queries in less than Y seconds from the current message
        maximum = (
            utils.config["settings"]["max_flood_cb_qrs_user"]
            if cb_qry.message.chat.type == "private"
            else utils.config["settings"]["max_flood_cb_qrs_chat"]
        )
        if (
            len(flood[cb_qry.message.chat.id][cb_qry.from_user.id]["cb_qrs_times"])
            >= maximum
        ):
            print(
                f"CALLBACK QUERIES FLOODER {cb_qry.from_user.id} IN {cb_qry.message.chat.id}"
            )
            flood_wait = 10
            # is the user flooding inside X seconds window after the previous flood_wait_expiry_date?
            if (
                flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                    "cb_qrs_flood_wait_expiry_date"
                ]
                and timestamp_
                <= flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                    "cb_qrs_flood_wait_expiry_date"
                ]
                + utils.config["settings"]["flood_surveillance_window"]
            ):
                if not utils.IsMaster(user_id=cb_qry.from_user.id):
                    # double previous_flood_wait time
                    flood_wait = (
                        flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                            "cb_qrs_previous_flood_wait"
                        ]
                        * 2
                    )

            flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                "cb_qrs_previous_flood_wait"
            ] = flood_wait
            # add previous_flood_wait current time to have an expiry date
            flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                "cb_qrs_flood_wait_expiry_date"
            ] = (
                timestamp_
                + flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                    "cb_qrs_previous_flood_wait"
                ]
            )
            text = _(cb_qry.from_user.settings.language, "flood_inline_warn")
            utils.Log(
                client=client,
                chat_id=cb_qry.message.chat.id,
                executer=client.ME.id,
                action="inline flood_wait of {0}".format(
                    flood[cb_qry.message.chat.id][cb_qry.from_user.id][
                        "cb_qrs_previous_flood_wait"
                    ]
                ),
                target=cb_qry.from_user.id,
            )
            # the show_alert parameter will probably slow down the user inhibiting flood
            methods.CallbackQueryAnswer(cb_qry=cb_qry, text=text, show_alert=True)
            # do not process callback_queries for flooders
            if cb_qry.id in punishments[cb_qry.message.chat.id]:
                punishments[cb_qry.message.chat.id].pop(cb_qry.id)
            cb_qry.stop_propagation()
    cb_qry.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.pinned_message & pyrogram.Filters.group, group=-1
)
def CheckPinnedMessages(client: pyrogram.Client, msg: pyrogram.Message):
    if msg.chat.settings.has_pin_markers:
        methods.ReplyText(client=client, msg=msg, text=f"#pin{abs(msg.chat.id)}")
    msg.continue_propagation()


@pyrogram.Client.on_message(
    pyrogram.Filters.group
    & (pyrogram.Filters.left_chat_member | pyrogram.Filters.new_chat_members),
    group=-1,
)
def CheckGroupMessageService(client: pyrogram.Client, msg: pyrogram.Message):
    if not msg.chat.settings.allow_service_messages:
        try:
            msg.delete()
        except pyrogram.errors.MessageDeleteForbidden as ex:
            print(ex)
            traceback.print_exc()
    msg.continue_propagation()
#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = "Julian Schrittwieser"

import json
import logging as log
import random
import re
from random import randrange
from time import sleep

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (Updater, CommandHandler, CallbackQueryHandler)

import Commands
from Constants.Cards import playerSets
from Constants.Config import TOKEN, STATS, ADMIN
from Boardgamebox.Game import Game
from Boardgamebox.Player import Player
import GamesController
import datetime

import os
import psycopg2
import urllib.parse

# Enable logging

log.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=log.INFO)


logger = log.getLogger(__name__)

#DB Connection I made a Haroku Postgres database first
urllib.parse.uses_netloc.append("postgres")
url = urllib.parse.urlparse(os.environ["DATABASE_URL"])

conn = psycopg2.connect(
    database=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port
)
'''
cur = conn.cursor()
query = "SELECT ...."
cur.execute(query)
'''

debugging = False

def initialize_testdata():
    # Sample game for quicker tests
    testgame = Game(-1001113216265, 15771023)
    GamesController.games[-1001113216265] = testgame
    players = [Player("Александр", 320853702), Player("Gustav", 305333239), Player("Rene", 318940765), Player("Susi", 290308460), Player("Renate", 312027975)]
    for player in players:
        testgame.add_player(player.uid, player)

##
#
# Beginning of round
#
##

def start_round(bot, game):        
        Commands.save_game(game.cid, "Saved Round %d" % (game.board.state.currentround + 1), game)
        log.info('start_round called')
        # Starting a new round makes the current round to go up    
        game.board.state.currentround += 1
        
        log.info(game.board.state.chosen_president)
        
        if game.board.state.chosen_president is None:
                game.board.state.nominated_president = game.player_sequence[game.board.state.player_counter]
        else:
                game.board.state.nominated_president = game.board.state.chosen_president
                game.board.state.chosen_president = None
        
        msgtext =  "The next presidential canditate is [%s](tg://user?id=%d).\n%s, please nominate a Chancellor in our private chat!" % (game.board.state.nominated_president.name, game.board.state.nominated_president.uid, game.board.state.nominated_president.name)
        bot.send_message(game.cid, msgtext, ParseMode.MARKDOWN)
        choose_chancellor(bot, game)
        # --> nominate_chosen_chancellor --> vote --> handle_voting --> count_votes --> voting_aftermath --> draw_policies
        # --> choose_policy --> pass_two_policies --> choose_policy --> enact_policy --> start_round


def choose_chancellor(bot, game):
    log.info('choose_chancellor called')
    strcid = str(game.cid)
    pres_uid = 0
    chan_uid = 0
    btns = []
    if game.board.state.president is not None:
        pres_uid = game.board.state.president.uid
    if game.board.state.chancellor is not None:
        chan_uid = game.board.state.chancellor.uid
    for uid in game.playerlist:
        # If there are only five players left in the
        # game, only the last elected Chancellor is
        # ineligible to be Chancellor Candidate; the
        # last President may be nominated.
        if len(game.player_sequence) > 5:
            if uid != game.board.state.nominated_president.uid and game.playerlist[
                uid].is_dead == False and uid != pres_uid and uid != chan_uid:
                name = game.playerlist[uid].name
                btns.append([InlineKeyboardButton(name, callback_data=strcid + "_chan_" + str(uid))])
        else:
            if uid != game.board.state.nominated_president.uid and game.playerlist[
                uid].is_dead == False and uid != chan_uid:
                name = game.playerlist[uid].name
                btns.append([InlineKeyboardButton(name, callback_data=strcid + "_chan_" + str(uid))])

    chancellorMarkup = InlineKeyboardMarkup(btns)
        #descomentar al entrar en produccion
        
    if(debugging):
        game.board.state.nominated_president.uid = ADMIN      
    bot.send_message(game.board.state.nominated_president.uid, game.board.print_board(game.player_sequence))
    bot.send_message(game.board.state.nominated_president.uid, 'Please nominate your chancellor!',
                     reply_markup=chancellorMarkup)


def nominate_chosen_chancellor(bot, update):
    log.info('nominate_chosen_chancellor called')
    log.info(update.callback_query.data)
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_chan_([0-9]*)", callback.data)
    cid = int(regex.group(1))
    chosen_uid = int(regex.group(2))
    if(debugging):
        chosen_uid = ADMIN   
    try:
        game = GamesController.games.get(cid, None)
        #log.info(game.playerlist)
        #log.info(str(chosen_uid) in game.playerlist )
        #log.info(chosen_uid in game.playerlist)        
        game.board.state.nominated_chancellor = game.playerlist[chosen_uid]
        log.info("President %s (%d) nominated %s (%d)" % (
                game.board.state.nominated_president.name, game.board.state.nominated_president.uid,
                game.board.state.nominated_chancellor.name, game.board.state.nominated_chancellor.uid))
        bot.edit_message_text("You nominated %s as Chancellor!" % game.board.state.nominated_chancellor.name,
                          callback.from_user.id, callback.message.message_id)
        bot.send_message(game.cid,
                     "President %s nominated %s as Chancellor. Please vote now!" % (
                         game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name))
        vote(bot, game)
    except AttributeError as e:
        log.error("nominate_chosen_chancellor: Game or board should not be None! Eror: " + str(e))
    except Exception as e:
        log.error("Unknown error: " + repr(e))
        log.exception(e)


def vote(bot, game):
        log.info('vote called')
        #When voting starts we start the counter to see later with the vote command if we can see you voted.
        game.dateinitvote = datetime.datetime.now()

        strcid = str(game.cid)
        btns = [[InlineKeyboardButton("Ja", callback_data=strcid + "_Ja"),
        InlineKeyboardButton("Nein", callback_data=strcid + "_Nein")]]
        voteMarkup = InlineKeyboardMarkup(btns)
        for uid in game.playerlist:
                if not game.playerlist[uid].is_dead and not debugging:
                        if game.playerlist[uid] is not game.board.state.nominated_president:
                        # the nominated president already got the board before nominating a chancellor
                                bot.send_message(uid, game.board.print_board(game.player_sequence))
                        bot.send_message(uid, "Do you want to elect President %s and Chancellor %s?" % (
                                game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name),
                                reply_markup=voteMarkup)


def handle_voting(bot, update):
    callback = update.callback_query
    log.info('handle_voting called: %s' % callback.data)
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = regex.group(2)
    strcid = regex.group(1)
    try:
        game = GamesController.games[cid]
        uid = callback.from_user.id
        bot.edit_message_text("Thank you for your vote: %s to a President %s and a Chancellor %s" % (
                answer, game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name), uid,
                        callback.message.message_id)
        log.info("Player %s (%d) voted %s" % (callback.from_user.first_name, uid, answer))
        
        #if uid not in game.board.state.last_votes:
        game.board.state.last_votes[uid] = answer
        
        #Allow player to change his vote
        btns = [[InlineKeyboardButton("Ja", callback_data=strcid + "_Ja"),
        InlineKeyboardButton("Nein", callback_data=strcid + "_Nein")]]
        voteMarkup = InlineKeyboardMarkup(btns)
        bot.send_message(uid, "You can change your vote here.\nDo you want to to elect President %s and Chancellor %s?" % (
                                game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name),
                                reply_markup=voteMarkup)
        #Commands.save_game(game.cid, "Saved Round %d" % (game.board.state.currentround), game)
        if len(game.board.state.last_votes) == len(game.player_sequence):
                count_votes(bot, game)
    except Exception as e:
        log.error(str(e))


def count_votes(bot, game):
    # La votacion ha finalizado.
    game.dateinitvote = None
    # La votacion ha finalizado.
    log.info('count_votes called')
    voting_text = ""
    voting_success = False
    for player in game.player_sequence:
        if game.board.state.last_votes[player.uid] == "Ja":
            voting_text += game.playerlist[player.uid].name + " voted Ja!\n"
        elif game.board.state.last_votes[player.uid] == "Nein":
            voting_text += game.playerlist[player.uid].name + " voted Nein!\n"
    if list(game.board.state.last_votes.values()).count("Ja") > (
        len(game.player_sequence) / 2):  # because player_sequence doesnt include dead
        # VOTING WAS SUCCESSFUL
        log.info("Voting successful")
        voting_text += "Hail President [%s](tg://user?id=%d)! Hail Chancellor [%s](tg://user?id=%d)!" % (
            game.board.state.nominated_president.name, game.board.state.nominated_president.uid, 
                game.board.state.nominated_chancellor.name, game.board.state.nominated_chancellor.uid)
        game.board.state.chancellor = game.board.state.nominated_chancellor
        game.board.state.president = game.board.state.nominated_president
        game.board.state.nominated_president = None
        game.board.state.nominated_chancellor = None
        voting_success = True
        bot.send_message(game.cid, voting_text, ParseMode.MARKDOWN)
        bot.send_message(game.cid, "\nYou can't talk now.")
        game.history.append(("Round %d.%d\n\n" % (game.board.state.liberal_track + game.board.state.fascist_track + 1, game.board.state.failed_votes + 1) ) + voting_text)
        log.info(game.history[game.board.state.currentround])
        voting_aftermath(bot, game, voting_success)
    else:
        log.info("Voting failed")
        voting_text += "The people didn't like President %s and Chancellor %s!" % (
            game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name)
        game.board.state.nominated_president = None
        game.board.state.nominated_chancellor = None
        game.board.state.failed_votes += 1
        bot.send_message(game.cid, voting_text)
        game.history.append(("Round %d.%d\n\n" % (game.board.state.liberal_track + game.board.state.fascist_track + 1, game.board.state.failed_votes) ) + voting_text)
        log.info(game.history[game.board.state.currentround])
        if game.board.state.failed_votes == 3:
            do_anarchy(bot, game)
        else:
            voting_aftermath(bot, game, voting_success)


def voting_aftermath(bot, game, voting_success):
    log.info('voting_aftermath called')
    game.board.state.last_votes = {}
    if voting_success:
        if game.board.state.fascist_track >= 3 and game.board.state.chancellor.role == "Hitler":
            # fascists win, because Hitler was elected as chancellor after 3 fascist policies
            game.board.state.game_endcode = -2
            end_game(bot, game, game.board.state.game_endcode)
        elif game.board.state.fascist_track >= 3 and game.board.state.chancellor.role != "Hitler" and game.board.state.chancellor not in game.board.state.not_hitlers:
            game.board.state.not_hitlers.append(game.board.state.chancellor)
            draw_policies(bot, game)
        else:
            # voting was successful and Hitler was not nominated as chancellor after 3 fascist policies
            draw_policies(bot, game)
    else:
        bot.send_message(game.cid, game.board.print_board(game.player_sequence))
        start_next_round(bot, game)


def draw_policies(bot, game):
    log.info('draw_policies called')
    strcid = str(game.cid)
    game.board.state.veto_refused = False
    # shuffle discard pile with rest if rest < 3
    shuffle_policy_pile(bot, game)
    btns = []
    for i in range(3):
        game.board.state.drawn_policies.append(game.board.policies.pop(0))
    for policy in game.board.state.drawn_policies:
        btns.append([InlineKeyboardButton(policy, callback_data=strcid + "_" + policy)])

    choosePolicyMarkup = InlineKeyboardMarkup(btns)    
    bot.send_message(game.board.state.president.uid,
                     "You drew the following 3 policies. Which one do you want to discard?",
                     reply_markup=choosePolicyMarkup)


def choose_policy(bot, update):
    log.info('choose_policy called')
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        game = GamesController.games[cid]
        strcid = str(game.cid)
        uid = callback.from_user.id
        if len(game.board.state.drawn_policies) == 3:
            log.info("Player %s (%d) discarded %s" % (callback.from_user.first_name, uid, answer))
            bot.edit_message_text("The policy %s will be discarded!" % answer, uid,
                                  callback.message.message_id)
            # remove policy from drawn cards and add to discard pile, pass the other two policies
            for i in range(3):
                if game.board.state.drawn_policies[i] == answer:
                    game.board.discards.append(game.board.state.drawn_policies.pop(i))
                    break
            pass_two_policies(bot, game)
        elif len(game.board.state.drawn_policies) == 2:
            if answer == "veto":
                log.info("Player %s (%d) suggested a veto" % (callback.from_user.first_name, uid))
                bot.edit_message_text("You suggested a Veto to President %s" % game.board.state.president.name, uid,
                                      callback.message.message_id)
                bot.send_message(game.cid,
                                 "Chancellor %s suggested a Veto to President %s." % (
                                     game.board.state.chancellor.name, game.board.state.president.name))

                btns = [[InlineKeyboardButton("Veto! (accept suggestion)", callback_data=strcid + "_yesveto")],
                        [InlineKeyboardButton("No Veto! (refuse suggestion)", callback_data=strcid + "_noveto")]]

                vetoMarkup = InlineKeyboardMarkup(btns)
                bot.send_message(game.board.state.president.uid,
                                 "Chancellor %s suggested a Veto to you. Do you want to veto (discard) these cards?" % game.board.state.chancellor.name,
                                 reply_markup=vetoMarkup)
            else:
                log.info("Player %s (%d) chose a %s policy" % (callback.from_user.first_name, uid, answer))
                bot.edit_message_text("The policy %s will be enacted!" % answer, uid,
                                      callback.message.message_id)
                # remove policy from drawn cards and enact, discard the other card
                for i in range(2):
                    if game.board.state.drawn_policies[i] == answer:
                        game.board.state.drawn_policies.pop(i)
                        break
                game.board.discards.append(game.board.state.drawn_policies.pop(0))
                assert len(game.board.state.drawn_policies) == 0
                enact_policy(bot, game, answer, False)
        else:
            log.error("choose_policy: drawn_policies should be 3 or 2, but was " + str(
                len(game.board.state.drawn_policies)))
    except:
        log.error("choose_policy: Game or board should not be None!")


def pass_two_policies(bot, game):
    log.info('pass_two_policies called')
    strcid = str(game.cid)
    btns = []
    for policy in game.board.state.drawn_policies:
        btns.append([InlineKeyboardButton(policy, callback_data=strcid + "_" + policy)])
    if game.board.state.fascist_track == 5 and not game.board.state.veto_refused:
        btns.append([InlineKeyboardButton("Veto", callback_data=strcid + "_veto")])
        choosePolicyMarkup = InlineKeyboardMarkup(btns)
        bot.send_message(game.cid,
                         "President %s gave two policies to Chancellor %s." % (
                             game.board.state.president.name, game.board.state.chancellor.name))
        bot.send_message(game.board.state.chancellor.uid,
                         "President %s gave you the following 2 policies. Which one do you want to enact? You can also use your Veto power." % game.board.state.president.name,
                         reply_markup=choosePolicyMarkup)
    elif game.board.state.veto_refused:
        choosePolicyMarkup = InlineKeyboardMarkup(btns)
        bot.send_message(game.board.state.chancellor.uid,
                         "President %s refused your Veto. Now you have to choose. Which one do you want to enact?" % game.board.state.president.name,
                         reply_markup=choosePolicyMarkup)
    elif game.board.state.fascist_track < 5:
        choosePolicyMarkup = InlineKeyboardMarkup(btns)
        bot.send_message(game.board.state.chancellor.uid,
                         "President %s gave you the following 2 policies. Which one do you want to enact?" % game.board.state.president.name,
                         reply_markup=choosePolicyMarkup)


def enact_policy(bot, game, policy, anarchy):
    log.info('enact_policy called')
    if policy == "liberal":
        game.board.state.liberal_track += 1
    elif policy == "fascist":
        game.board.state.fascist_track += 1
    game.board.state.failed_votes = 0  # reset counter
    if not anarchy:
        bot.send_message(game.cid,
                         "President %s and Chancellor %s enacted a %s policy!" % (
                             game.board.state.president.name, game.board.state.chancellor.name, policy))
        game.history[game.board.state.currentround] += "\n\nPresident %s and Chancellor %s enacted a %s policy!" % (
                             game.board.state.president.name, game.board.state.chancellor.name, policy)
    else:
        bot.send_message(game.cid,
                         "The top most policy was enacted: %s" % policy)
        game.history[game.board.state.currentround] += "\n\nThe top most policy was enacted: %s" % policy
    sleep(3)
    bot.send_message(game.cid, game.board.print_board(game.player_sequence))
    # end of round
    if game.board.state.liberal_track == 5:
        game.board.state.game_endcode = 1
        end_game(bot, game, game.board.state.game_endcode)  # liberals win with 5 liberal policies
    if game.board.state.fascist_track == 6:
        game.board.state.game_endcode = -1
        end_game(bot, game, game.board.state.game_endcode)  # fascists win with 6 fascist policies
    sleep(3)
    # End of legislative session, shuffle if necessary 
    shuffle_policy_pile(bot, game)    
    if not anarchy:
        if policy == "fascist":
            action = game.board.fascist_track_actions[game.board.state.fascist_track - 1]
            if action is None and game.board.state.fascist_track == 6:
                pass
            elif action == None:
                start_next_round(bot, game)
            elif action == "policy":
                bot.send_message(game.cid,
                                 "Presidential Power enabled: Policy Peek " + u"\U0001F52E" + "\nPresident %s now knows the next three policies on "
                                                                                              "the pile.  The President may share "
                                                                                              "(or lie about!) the results of their "
                                                                                              "investigation at their discretion." % game.board.state.president.name)
                game.history[game.board.state.currentround] += "\n\nPresident %s now knows the next three policies on the pile" % game.board.state.president.name
                action_policy(bot, game)                
            elif action == "kill":
                bot.send_message(game.cid,
                                 "Presidential Power enabled: Execution " + u"\U0001F5E1" + "\nPresident %s has to kill one person. You can "
                                                                                            "discuss the decision now but the "
                                                                                            "President has the final say." % game.board.state.president.name)
                action_kill(bot, game)
            elif action == "inspect":
                bot.send_message(game.cid,
                                 "Presidential Power enabled: Investigate Loyalty " + u"\U0001F50E" + "\nPresident %s may see the party membership of one "
                                                                                                      "player. The President may share "
                                                                                                      "(or lie about!) the results of their "
                                                                                                      "investigation at their discretion." % game.board.state.president.name)
                action_inspect(bot, game)
            elif action == "choose":
                bot.send_message(game.cid,
                                 "Presidential Power enabled: Call Special Election " + u"\U0001F454" + "\nPresident %s gets to choose the next presidential "
                                                                                                        "candidate. Afterwards the order resumes "
                                                                                                        "back to normal." % game.board.state.president.name)
                action_choose(bot, game)
        else:
            start_next_round(bot, game)
    else:
        start_next_round(bot, game)


def choose_veto(bot, update):
    log.info('choose_veto called')
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        game = GamesController.games[cid]
        uid = callback.from_user.id
        if answer == "yesveto":
            log.info("Player %s (%d) accepted the veto" % (callback.from_user.first_name, uid))
            bot.edit_message_text("You accepted the Veto!", uid, callback.message.message_id)
            bot.send_message(game.cid,
                             "President %s accepted Chancellor %s's Veto. No policy was enacted but this counts as a failed election." % (
                                 game.board.state.president.name, game.board.state.chancellor.name))
            game.board.discards += game.board.state.drawn_policies
            game.board.state.drawn_policies = []
            game.board.state.failed_votes += 1
            shuffle_policy_pile(bot, game)  
            if game.board.state.failed_votes == 3:
                do_anarchy(bot, game)
            else:
                bot.send_message(game.cid, game.board.print_board(game.player_sequence))
                start_next_round(bot, game)
        elif answer == "noveto":
            log.info("Player %s (%d) declined the veto" % (callback.from_user.first_name, uid))
            game.board.state.veto_refused = True
            bot.edit_message_text("You refused the Veto!", uid, callback.message.message_id)
            bot.send_message(game.cid,
                             "President %s refused Chancellor %s's Veto. The Chancellor now has to choose a policy!" % (
                                 game.board.state.president.name, game.board.state.chancellor.name))
            pass_two_policies(bot, game)
        else:
            log.error("choose_veto: Callback data can either be \"veto\" or \"noveto\", but not %s" % answer)
    except:
        log.error("choose_veto: Game or board should not be None!")


def do_anarchy(bot, game):
    #log.info('do_anarchy called')
    bot.send_message(game.cid, game.board.print_board(game.player_sequence))
    bot.send_message(game.cid, "ANARCHY!!")
    game.board.state.president = None
    game.board.state.chancellor = None
    top_policy = game.board.policies.pop(0)
    game.board.state.last_votes = {}
    enact_policy(bot, game, top_policy, True)


def action_policy(bot, game):
    log.info('action_policy called')
    topPolicies = ""
    # shuffle discard pile with rest if rest < 3
    shuffle_policy_pile(bot, game)
    for i in range(3):
        topPolicies += game.board.policies[i] + "\n"
    bot.send_message(game.board.state.president.uid,
                     "The top three polices are (top most first):\n%s\nYou may lie about this." % topPolicies)
    start_next_round(bot, game)


def action_kill(bot, game):
    log.info('action_kill called')
    strcid = str(game.cid)
    btns = []
    for uid in game.playerlist:
        if uid != game.board.state.president.uid and game.playerlist[uid].is_dead == False:
            name = game.playerlist[uid].name
            btns.append([InlineKeyboardButton(name, callback_data=strcid + "_kill_" + str(uid))])

    killMarkup = InlineKeyboardMarkup(btns)
    bot.send_message(game.board.state.president.uid, game.board.print_board(game.player_sequence))
    bot.send_message(game.board.state.president.uid,
                     'You have to kill one person. You can discuss your decision with the others. Choose wisely!',
                     reply_markup=killMarkup)


def choose_kill(bot, update):
    log.info('choose_kill called')
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_kill_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = int(regex.group(2))
    try:
        game = GamesController.games[cid]
        chosen = game.playerlist[answer]
        chosen.is_dead = True
        if game.player_sequence.index(chosen) <= game.board.state.player_counter:
            game.board.state.player_counter -= 1
        game.player_sequence.remove(chosen)
        game.board.state.dead += 1
        log.info("Player %s (%d) killed %s (%d)" % (
            callback.from_user.first_name, callback.from_user.id, chosen.name, chosen.uid))
        bot.edit_message_text("You killed %s!" % chosen.name, callback.from_user.id, callback.message.message_id)
        if chosen.role == "Hitler":
            bot.send_message(game.cid, "President " + game.board.state.president.name + " killed " + chosen.name + ". ")
            end_game(bot, game, 2)
        else:
            bot.send_message(game.cid,
                             "President %s killed %s who was not Hitler. %s, you are dead now and are not allowed to talk anymore!" % (
                                 game.board.state.president.name, chosen.name, chosen.name))
            bot.send_message(game.cid, game.board.print_board(game.player_sequence))
            game.history[game.board.state.currentround] += "\n\nPresident %s killed %s who was not Hitler!" % (
                                 game.board.state.president.name, chosen.name)
            start_next_round(bot, game)
    except:
        log.error("choose_kill: Game or board should not be None!")


def action_choose(bot, game):
    log.info('action_choose called')
    strcid = str(game.cid)
    btns = []

    for uid in game.playerlist:
        if uid != game.board.state.president.uid and game.playerlist[uid].is_dead == False:
            name = game.playerlist[uid].name
            btns.append([InlineKeyboardButton(name, callback_data=strcid + "_choo_" + str(uid))])

    inspectMarkup = InlineKeyboardMarkup(btns)
    bot.send_message(game.board.state.president.uid, game.board.print_board(game.player_sequence))
    bot.send_message(game.board.state.president.uid,
                     'You get to choose the next presidential candidate. Afterwards the order resumes back to normal. Choose wisely!',
                     reply_markup=inspectMarkup)


def choose_choose(bot, update):
    log.info('choose_choose called')
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_choo_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = int(regex.group(2))
    try:
        game = GamesController.games[cid]
        chosen = game.playerlist[answer]
        game.board.state.chosen_president = chosen
        log.info(
            "Player %s (%d) chose %s (%d) as next president" % (
                callback.from_user.first_name, callback.from_user.id, chosen.name, chosen.uid))
        bot.edit_message_text("You chose %s as the next president!" % chosen.name, callback.from_user.id,
                              callback.message.message_id)
        bot.send_message(game.cid,
                         "President %s chose %s as the next president." % (
                             game.board.state.president.name, chosen.name))
        game.history[game.board.state.currentround] += "\n\nPresident %s chose %s as the next president." % (
                game.board.state.president.name, chosen.name)
        start_next_round(bot, game)
    except:
        log.error("choose_choose: Game or board should not be None!")


def action_inspect(bot, game):
    log.info('action_inspect called')
    strcid = str(game.cid)
    btns = []
    for uid in game.playerlist:
        if uid != game.board.state.president.uid and game.playerlist[uid].is_dead == False:
            name = game.playerlist[uid].name
            btns.append([InlineKeyboardButton(name, callback_data=strcid + "_insp_" + str(uid))])

    inspectMarkup = InlineKeyboardMarkup(btns)
    bot.send_message(game.board.state.president.uid, game.board.print_board(game.player_sequence))
    bot.send_message(game.board.state.president.uid,
                     'You may see the party membership of one player. Which do you want to know? Choose wisely!',
                     reply_markup=inspectMarkup)


def choose_inspect(bot, update):
    log.info('choose_inspect called')
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_insp_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = int(regex.group(2))
    try:
        game = GamesController.games[cid]
        chosen = game.playerlist[answer]
        log.info(
            "Player %s (%d) inspects %s (%d)'s party membership (%s)" % (
                callback.from_user.first_name, callback.from_user.id, chosen.name, chosen.uid,
                chosen.party))
        bot.edit_message_text("The party membership of %s is %s" % (chosen.name, chosen.party),
                              callback.from_user.id,
                              callback.message.message_id)
        bot.send_message(game.cid, "President %s inspected %s." % (game.board.state.president.name, chosen.name))
        game.history[game.board.state.currentround] += "\n\nPresident %s inspected %s." % (game.board.state.president.name, chosen.name)
        start_next_round(bot, game)
    except:
        log.error("choose_inspect: Game or board should not be None!")


def start_next_round(bot, game):
    log.info('start_next_round called')
    # start next round if there is no winner (or /cancel)
    if game.board.state.game_endcode == 0:
        # start new round
        sleep(5)
        # if there is no special elected president in between
        if game.board.state.chosen_president is None:
            increment_player_counter(game)
        start_round(bot, game)


##
#
# End of round
#
##

def end_game(bot, game, game_endcode):
        log.info('end_game called')
        ##
        # game_endcode:
        #   -2  fascists win by electing Hitler as chancellor
        #   -1  fascists win with 6 fascist policies
        #   0   not ended
        #   1   liberals win with 5 liberal policies
        #   2   liberals win by killing Hitler
        #   99  game cancelled
        #
        if game_endcode == 99:
                if GamesController.games[game.cid].board is not None:
                        bot.send_message(game.cid, "Game cancelled!\n\n%s" % game.print_roles())
                else:
                        bot.send_message(game.cid, "Game cancelled!")
        else:
                if game_endcode == -2:
                        bot.send_message(game.cid, "Game over! The fascists win by electing Hitler as Chancellor!\n\n%s" % game.print_roles())
                if game_endcode == -1:
                        bot.send_message(game.cid, "Game over! The fascists win by enacting 6 fascist policies!\n\n%s" % game.print_roles())
                if game_endcode == 1:
                        bot.send_message(game.cid, "Game over! The liberals win by enacting 5 liberal policies!\n\n%s" % game.print_roles())
                if game_endcode == 2:
                        bot.send_message(game.cid, "Game over! The liberals win by killing Hitler!\n\n%s" % game.print_roles())
        del GamesController.games[game.cid]
        Commands.delete_game(game.cid)
        
def inform_players(bot, game, cid, player_number):
    log.info('inform_players called')
    bot.send_message(cid,
                     "Let's start the game with %d players!\n%s\nGo to your private chat and look at your secret role!" % (
                         player_number, print_player_info(player_number)))
    available_roles = list(playerSets[player_number]["roles"])  # copy not reference because we need it again later
    for uid in game.playerlist:
        random_index = randrange(len(available_roles))
        #log.info(str(random_index))
        role = available_roles.pop(random_index)
        #log.info(str(role))
        party = get_membership(role)
        game.playerlist[uid].role = role
        game.playerlist[uid].party = party
        # I comment so tyhe player aren't discturbed in testing, uncomment when deploy to production
        if not debugging:
                bot.send_message(uid, "Your secret role is: %s\nYour party membership is: %s" % (role, party))
        else:
                bot.send_message(ADMIN, "Player %s role is %s and party membership is: %s" % (game.playerlist[uid].name, role, party))


def print_player_info(player_number):
    if player_number == 5:
        return "There are 3 Liberals, 1 Fascist and Hitler. Hitler knows who the Fascist is."
    elif player_number == 6:
        return "There are 4 Liberals, 1 Fascist and Hitler. Hitler knows who the Fascist is."
    elif player_number == 7:
        return "There are 4 Liberals, 2 Fascist and Hitler. Hitler doesn't know who the Fascists are."
    elif player_number == 8:
        return "There are 5 Liberals, 2 Fascist and Hitler. Hitler doesn't know who the Fascists are."
    elif player_number == 9:
        return "There are 5 Liberals, 3 Fascist and Hitler. Hitler doesn't know who the Fascists are."
    elif player_number == 10:
        return "There are 6 Liberals, 3 Fascist and Hitler. Hitler doesn't know who the Fascists are."


def inform_fascists(bot, game, player_number):
    log.info('inform_fascists called')

    for uid in game.playerlist:
        role = game.playerlist[uid].role
        if role == "Fascist":
            fascists = game.get_fascists()
            if player_number > 6:
                fstring = ""
                for f in fascists:
                    if f.uid != uid:
                        fstring += f.name + ", "
                fstring = fstring[:-2]
                if not debugging:
                        bot.send_message(uid, "Your fellow fascists are: %s" % fstring)
            hitler = game.get_hitler()
            if not debugging:
                        bot.send_message(uid, "Hitler is: %s" % hitler.name) #Uncoomend on production
        elif role == "Hitler":
            if player_number <= 6:
                fascists = game.get_fascists()
                if not debugging:
                        bot.send_message(uid, "Your fellow fascist is: %s" % fascists[0].name)
        elif role == "Liberal":
            pass
        else:
            log.error("inform_fascists: can\'t handle the role %s" % role)


def get_membership(role):
    log.info('get_membership called')
    if role == "Fascist" or role == "Hitler":
        return "fascist"
    elif role == "Liberal":
        return "liberal"
    else:
        return None


def increment_player_counter(game):
    log.info('increment_player_counter called')
    if game.board.state.player_counter < len(game.player_sequence) - 1:
        game.board.state.player_counter += 1
    else:
        game.board.state.player_counter = 0


def shuffle_policy_pile(bot, game):
    log.info('shuffle_policy_pile called')
    if len(game.board.policies) < 3:
        game.history[game.board.state.currentround] += "\n\nThere were not enough cards left on the policy pile so I shuffled the rest with the discard pile!"
        game.board.discards += game.board.policies
        game.board.policies = random.sample(game.board.discards, len(game.board.discards))
        game.board.discards = []
        bot.send_message(game.cid,
                         "There were not enough cards left on the policy pile so I shuffled the rest with the discard pile!")


def error(bot, update, error):
    #bot.send_message(387393551, 'Update "%s" caused error "%s"' % (update, error) ) 
    logger.warning('Update "%s" caused error "%s"' % (update, error))

def main():
        GamesController.init() #Call only once
        #initialize_testdata()
        
        #Init DB Create tables if they don't exist   
        log.info('Init DB')
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(open("DBCreate.sql", "r").read())
        log.info('DB Created/Updated')
        conn.autocommit = False
        '''
        log.info('Insertando')
        query = "INSERT INTO users(facebook_id, name , access_token , created) values ('2','3','4',1) RETURNING id;"
        log.info('Por ejecutar')
        cur.execute(query)       
        user_id = cur.fetchone()[0]        
        log.info(user_id)
        
        
        query = "SELECT ...."
        cur.execute(query)
        '''
        
        #PORT = int(os.environ.get('PORT', '5000'))
        updater = Updater(TOKEN)
        '''
        updater.start_webhook(listen="0.0.0.0",
                      port=PORT,
                      url_path=TOKEN)
        updater.bot.set_webhook("https://secrethitlertest.herokuapp.com/" + TOKEN)
        '''
        
        # Get the dispatcher to register handlers
        dp = updater.dispatcher

        # on different commands - answer in Telegram
        dp.add_handler(CommandHandler("start", Commands.command_start))
        dp.add_handler(CommandHandler("help", Commands.command_help))
        dp.add_handler(CommandHandler("board", Commands.command_board))
        dp.add_handler(CommandHandler("rules", Commands.command_rules))
        dp.add_handler(CommandHandler("ping", Commands.command_ping))
        dp.add_handler(CommandHandler("symbols", Commands.command_symbols))
        dp.add_handler(CommandHandler("stats", Commands.command_stats))
        dp.add_handler(CommandHandler("newgame", Commands.command_newgame))
        dp.add_handler(CommandHandler("startgame", Commands.command_startgame))
        dp.add_handler(CommandHandler("cancelgame", Commands.command_cancelgame))
        dp.add_handler(CommandHandler("join", Commands.command_join, pass_args = True))
        dp.add_handler(CommandHandler("history", Commands.command_showhistory))
        dp.add_handler(CommandHandler("votes", Commands.command_votes))
        dp.add_handler(CommandHandler("calltovote", Commands.command_calltovote))
        dp.add_handler(CommandHandler("claim", Commands.command_claim, pass_args = True))
        
        #Testing commands
        dp.add_handler(CommandHandler("ja", Commands.command_ja))
        dp.add_handler(CommandHandler("nein", Commands.command_nein))

        dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_chan_(.*)", callback=nominate_chosen_chancellor))
        dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_insp_(.*)", callback=choose_inspect))
        dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_choo_(.*)", callback=choose_choose))
        dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_kill_(.*)", callback=choose_kill))
        dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(yesveto|noveto)", callback=choose_veto))
        dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(liberal|fascist|veto)", callback=choose_policy))
        dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(Ja|Nein)", callback=handle_voting))


        # log all errors
        dp.add_error_handler(error)

        # Start the Bot
        updater.start_polling()

        # Run the bot until the you presses Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        updater.idle()



if __name__ == '__main__':
    main()

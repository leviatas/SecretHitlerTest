#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = "Julian Schrittwieser,  Leviatas"

import json
import logging as log
import random
import re
from random import randrange
from time import sleep

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.ext import (Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext)


import Commands
from Constants.Cards import playerSets
from Constants.Config import ADMIN
from Boardgamebox.Game import Game
from Boardgamebox.Player import Player
from PlayerStats import PlayerStats
import GamesController
import datetime
import jsonpickle
import os
import psycopg2
from psycopg2 import sql
import urllib.parse

import traceback
import sys
from telegram.utils.helpers import mention_html
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
	
	if game.board.state.chosen_president is None:
		game.board.state.nominated_president = game.player_sequence[game.board.state.player_counter]
	else:
		game.board.state.nominated_president = game.board.state.chosen_president
		game.board.state.chosen_president = None

	Commands.print_board(bot, game, game.cid)
	msgtext =  "El próximo candidato a presidente es [%s](tg://user?id=%d).\n%s, por favor nomina a un canciller en nuestro chat privado!" % (game.board.state.nominated_president.name, game.board.state.nominated_president.uid, game.board.state.nominated_president.name)
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
			if uid != game.board.state.nominated_president.uid and game.playerlist[uid].is_dead == False and uid != pres_uid and uid != chan_uid:
				name = game.playerlist[uid].name
				btns.append([InlineKeyboardButton(name, callback_data=strcid + "_chan_" + str(uid))])
		else:
			if uid != game.board.state.nominated_president.uid and game.playerlist[uid].is_dead == False and uid != chan_uid:
				name = game.playerlist[uid].name
				btns.append([InlineKeyboardButton(name, callback_data=strcid + "_chan_" + str(uid))])

	chancellorMarkup = InlineKeyboardMarkup(btns)
	#descomentar al entrar en produccion

	if game.is_debugging:
		Commands.print_board(bot, game, ADMIN)
		bot.send_message(ADMIN, 'Por favor nomina a tu canciller!', parse_mode=ParseMode.MARKDOWN, reply_markup=chancellorMarkup)      
	else:
		Commands.print_board(bot, game, game.board.state.nominated_president.uid)
		groupName = ""
		if hasattr(game, 'groupName'):
			groupName += "*En el grupo {}*\n".format(game.groupName)
		msg = '{}Por favor nomina a tu canciller!'.format(groupName)
		bot.send_message(game.board.state.nominated_president.uid, msg, parse_mode=ParseMode.MARKDOWN, reply_markup=chancellorMarkup)

	game.board.state.fase = "choose_chancellor"
	Commands.save_game(game.cid, "choose_chancellor Round %d" % (game.board.state.currentround), game)

def nominate_chosen_chancellor(update: Update, context: CallbackContext):
	bot = context.bot
	log.info('nominate_chosen_chancellor called')
	log.info(update.callback_query.data)
	callback = update.callback_query
	regex = re.search("(-[0-9]*)_chan_([0-9]*)", callback.data)
	cid = int(regex.group(1))
	chosen_uid = int(regex.group(2))
	#if(game.is_debugging):
	#    chosen_uid = ADMIN   
	try:
		game = Commands.get_game(cid)

		if callback.from_user.id != game.board.state.nominated_president.uid:
			bot.edit_message_text("No eres el presidente actual, no puedes nominar!", callback.from_user.id, callback.message.message_id)
			return

		game.board.state.nominated_chancellor = game.playerlist[chosen_uid]
		log.info("El Presidente %s (%d) nominó a %s (%d)" % (
					game.board.state.nominated_president.name, game.board.state.nominated_president.uid,
					game.board.state.nominated_chancellor.name, game.board.state.nominated_chancellor.uid))
		bot.edit_message_text("Tú nominaste a %s como canciller!" % game.board.state.nominated_chancellor.name,
					callback.from_user.id, callback.message.message_id)
		bot.send_message(game.cid,
					"El presidente %s nominó a %s como canciller. Por favor, vota ahora!" % (
					game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name))
		vote(bot, game)
		# Save after voting buttons send and set phase voting
		game.board.state.fase = "vote"
		Commands.save_game(game.cid, "vote Round %d" % (game.board.state.currentround), game)
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
		if not game.playerlist[uid].is_dead and not game.is_debugging:
			if game.playerlist[uid] is not game.board.state.nominated_president:
				# the nominated president already got the board before nominating a chancellor
				Commands.print_board(bot, game, uid)
			groupName = ""		
			if hasattr(game, 'groupName'):
				groupName += "*En el grupo {}*\n".format(game.groupName)
			msg = "{}Quieres elegir al Presidente *{}* y al canciller *{}*?".format(groupName, game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name)
			bot.send_message(uid, msg,	reply_markup=voteMarkup, parse_mode=ParseMode.MARKDOWN)


def handle_voting(update: Update, context: CallbackContext):
	bot = context.bot
	callback = update.callback_query
	log.info('handle_voting called: %s' % callback.data)
	regex = re.search("(-[0-9]*)_(.*)", callback.data)
	cid = int(regex.group(1))
	answer = regex.group(2)
	strcid = regex.group(1)
	try:
		game = Commands.get_game(cid)
		uid = callback.from_user.id
		#
		if game.dateinitvote is None:
			bot.edit_message_text("No es el momento de votar!", uid, callback.message.message_id)
			return

		bot.edit_message_text("Gracias por tu voto: %s para el Presidente %s y el canciller %s" % (
			answer, game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name), uid,
			callback.message.message_id)
		log.info("Player %s (%d) voted %s" % (callback.from_user.first_name, uid, answer))

		#if uid not in game.board.state.last_votes:
		game.board.state.last_votes[uid] = answer

		#Allow player to change his vote
		btns = [[InlineKeyboardButton("Ja", callback_data=strcid + "_Ja"),
				InlineKeyboardButton("Nein", callback_data=strcid + "_Nein")]]
		voteMarkup = InlineKeyboardMarkup(btns)
		 
		groupName = ""
		
		if hasattr(game, 'groupName'):
			groupName += "*En el grupo {}*\n".format(game.groupName)

		msg = "{}\nPuedes cambiar tu voto aquí.\nQuieres elegir al Presidente *{}* y al canciller *{}*?".format(groupName, game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name)
		bot.send_message(uid, msg, reply_markup=voteMarkup, parse_mode=ParseMode.MARKDOWN)
		Commands.save_game(game.cid, "vote Round %d" % (game.board.state.currentround), game)
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
		nombre_jugador = game.playerlist[player.uid].name.replace("_", " ")
		if game.board.state.last_votes[player.uid] == "Ja":
			voting_text += nombre_jugador + " votó Ja!\n"
		elif game.board.state.last_votes[player.uid] == "Nein":
			voting_text += nombre_jugador + " votó Nein!\n"
	if list(game.board.state.last_votes.values()).count("Ja") > (
		len(game.player_sequence) / 2):  # because player_sequence doesnt include dead
		# VOTING WAS SUCCESSFUL
		log.info("Voting successful")
		voting_text += "Hail Presidente [%s](tg://user?id=%d)! Hail Canciller [%s](tg://user?id=%d)!" % (
			game.board.state.nominated_president.name, game.board.state.nominated_president.uid, 
				game.board.state.nominated_chancellor.name, game.board.state.nominated_chancellor.uid)
		game.board.state.chancellor = game.board.state.nominated_chancellor
		game.board.state.president = game.board.state.nominated_president
		game.board.state.nominated_president = None
		game.board.state.nominated_chancellor = None
		voting_success = True
		
		bot.send_message(game.cid, voting_text, ParseMode.MARKDOWN)
		bot.send_message(game.cid, "\nNo se puede hablar ahora.")
		game.history.append(("Ronda %d.%d\n\n" % (game.board.state.liberal_track + game.board.state.fascist_track + 1, game.board.state.failed_votes + 1) ) + voting_text)
		#log.info(game.history[game.board.state.currentround])
		voting_aftermath(bot, game, voting_success)
	else:
		log.info("Voting failed")
		voting_text += "Al pueblo no les gusto el Presidente %s y el canciller %s!" % (
			game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name)
		game.board.state.nominated_president = None
		game.board.state.nominated_chancellor = None
		game.board.state.failed_votes += 1
		bot.send_message(game.cid, voting_text)
		game.history.append(("Ronda %d.%d\n\n" % (game.board.state.liberal_track + game.board.state.fascist_track + 1, game.board.state.failed_votes) ) + voting_text)
		#log.info(game.history[game.board.state.currentround])
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
		else:
			if game.board.state.fascist_track >= 3 and game.board.state.chancellor.role != "Hitler" and game.board.state.chancellor not in game.board.state.not_hitlers:
				game.board.state.not_hitlers.append(game.board.state.chancellor)
			# voting was successful and Hitler was not nominated as chancellor after 3 fascist policies
			draw_policies(bot, game)
	else:
		#Commands.print_board(bot, game, game.cid)
		start_next_round(bot, game)


def draw_policies(bot, game):
	log.info('draw_policies called')
	strcid = str(game.cid)
	game.board.state.veto_refused = False
	# shuffle discard pile with rest if rest < 3
	shuffle_policy_pile(bot, game)
	btns = []
	hiddenhistory_text = ""
	for i in range(3):
		game.board.state.drawn_policies.append(game.board.policies.pop(0))
	for policy in game.board.state.drawn_policies:
		btns.append([InlineKeyboardButton(policy, callback_data=strcid + "_" + policy)])
		hiddenhistory_text += policy.title() + " "
	hiddenhistory_text[:-1]
	# Guardo Historial secreto
	game.hiddenhistory.append(("*Ronda %d.%d*\nEl presidente %s recibió " % (game.board.state.liberal_track + game.board.state.fascist_track + 1, game.board.state.failed_votes + 1, game.board.state.president.name) ) + hiddenhistory_text)
	choosePolicyMarkup = InlineKeyboardMarkup(btns)
	if not game.is_debugging:
		bot.send_message(game.board.state.president.uid, "Has robado las siguientes 3 politicas. Cual quieres descartar?",
			reply_markup=choosePolicyMarkup)
	else:
		bot.send_message(ADMIN, "Has robado las siguientes 3 politicas. Cual quieres descartar?",
			reply_markup=choosePolicyMarkup)
	game.board.state.fase = "legislating president discard"
	Commands.save_game(game.cid, "legislating president discard Round %d" % (game.board.state.currentround), game)

def choose_policy(update: Update, context: CallbackContext):
	bot = context.bot
	log.info('choose_policy called')
	callback = update.callback_query
	regex = re.search("(-[0-9]*)_(.*)", callback.data)
	cid = int(regex.group(1))
	answer = regex.group(2)
	try:
		game = Commands.get_game(cid)	
		strcid = str(game.cid)
		uid = callback.from_user.id

		# Solo el presidente y el canciller pueden elegir politica.
		if uid not in [game.board.state.chancellor.uid, game.board.state.president.uid]:
			msg = "No eres ni el presidente ni el canciller actual!"
			bot.edit_message_text(msg, uid,	callback.message.message_id)
			return

		# Si hay 3 politicas veo que sea el presidente el que descarte.
		if len(game.board.state.drawn_policies) == 3 and uid == game.board.state.president.uid:
			log.info("Player %s (%d) discarded %s" % (callback.from_user.first_name, uid, answer))
			bot.edit_message_text("La política %s va a ser descartada!" % answer, uid,
			callback.message.message_id)
			# remove policy from drawn cards and add to discard pile, pass the other two policies
			# Grabo en Hidden History que descarta el presidente.
			game.hiddenhistory.append("El presidente descartó " + answer)
			for i in range(3):
				if game.board.state.drawn_policies[i] == answer:
					game.board.discards.append(game.board.state.drawn_policies.pop(i))                                
					break
			pass_two_policies(bot, game)
		elif len(game.board.state.drawn_policies) == 2 and uid == game.board.state.chancellor.uid:
			# Si el canciller elije el boton de veto
			if answer == "veto" :
				log.info("Player %s (%d) suggested a veto" % (callback.from_user.first_name, uid))
				bot.edit_message_text("Has sugerido vetar al Presidente %s" % game.board.state.president.name, uid,
					callback.message.message_id)
				bot.send_message(game.cid,
					"El canciller %s sugirío Vetar al Presidente %s." % (
					game.board.state.chancellor.name, game.board.state.president.name))

				btns = [[InlineKeyboardButton("Veto! (aceptar sugerencia)", callback_data=strcid + "_yesveto")],
				[InlineKeyboardButton("No Veto! (rechazar sugerencia)", callback_data=strcid + "_noveto")]]

				vetoMarkup = InlineKeyboardMarkup(btns)
				bot.send_message(game.board.state.president.uid,
					"El canciller %s te sugirío Vetar. Quieres vetar (descartar) estas cartas?" % game.board.state.chancellor.name,
					reply_markup=vetoMarkup)
			else:
				# Si el canciller promulga...
				log.info("Player %s (%d) chose a %s policy" % (callback.from_user.first_name, uid, answer))
				bot.edit_message_text("La politica %s será promulgada!" % answer, uid,
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
	except Exception as e:
		log.error("choose_policy:" + str(e))

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
			"El presidente %s entregó dos políticas al Canciller %s." % (
			game.board.state.president.name, game.board.state.chancellor.name))
		bot.send_message(game.board.state.chancellor.uid,
			"El Presidente %s te entregó las siguientes 2 políticas. Cuál quieres promulgar? También puedes usar el poder de Veto." % game.board.state.president.name,
		reply_markup=choosePolicyMarkup)
	elif game.board.state.veto_refused:
		choosePolicyMarkup = InlineKeyboardMarkup(btns)
		bot.send_message(game.board.state.chancellor.uid,
			"El presidente %s ha rechazado tu Veto. Ahora tienes que elegir. Cuál quieres promulgar?" % game.board.state.president.name,
			reply_markup=choosePolicyMarkup)
	elif game.board.state.fascist_track < 5:
		bot.send_message(game.cid,
			"El presidente %s entregó dos políticas al Canciller %s." % (
			game.board.state.president.name, game.board.state.chancellor.name))
		choosePolicyMarkup = InlineKeyboardMarkup(btns)
		if not game.is_debugging:
			bot.send_message(game.board.state.chancellor.uid,
				"El Presidente %s te entregó las siguientes 2 políticas. Cuál quieres promulgar?" % game.board.state.president.name,
				reply_markup=choosePolicyMarkup)
		else:
			bot.send_message(ADMIN,
				"El Presidente %s te entregó las siguientes 2 políticas. Cuál quieres promulgar?" % game.board.state.president.name,
				reply_markup=choosePolicyMarkup)	
	
	game.board.state.fase = "legislating choose chancellor"
	Commands.save_game(game.cid, "legislating choose chancellor Round %d" % (game.board.state.currentround), game)

def enact_policy(bot, game, policy, anarchy):
	log.info('enact_policy called')
	if policy == "liberal":
		game.board.state.liberal_track += 1
	elif policy == "fascista":
		game.board.state.fascist_track += 1
	game.board.state.failed_votes = 0  # reset counter
	if not anarchy:
		bot.send_message(game.cid, "El Presidente %s y el Canciller %s promulgaron una política %s!" % (game.board.state.president.name, game.board.state.chancellor.name, policy))
		game.history.append("El Presidente %s y el Canciller %s promulgaron una política %s!" % (game.board.state.president.name, game.board.state.chancellor.name, policy))
	else:
		bot.send_message(game.cid, "La política en la cima del mazo ha sido promulgada y es %s" % policy)
		game.history.append("La política en la cima del mazo ha sido promulgada y es %s" % policy)
	#sleep(2)    
	# end of round
	if game.board.state.liberal_track == 5:
		game.board.state.game_endcode = 1
		end_game(bot, game, game.board.state.game_endcode)  # liberals win with 5 liberal policies
	if game.board.state.fascist_track == 6:
		game.board.state.game_endcode = -1
		end_game(bot, game, game.board.state.game_endcode)  # fascists win with 6 fascist policies
	#sleep(3)
	# End of legislative session, shuffle if necessary 
	shuffle_policy_pile(bot, game)    
	if not anarchy:
		if policy == "fascista":
			action = game.board.fascist_track_actions[game.board.state.fascist_track - 1]
			if action is None and game.board.state.fascist_track == 6:
				pass
			elif action == None:
				start_next_round(bot, game)
			elif action == "policy":
				bot.send_message(game.cid,
					"Poder Presidencial habilitado: Investigar Políticas " + u"\U0001F52E" + "\nEl Presidente %s ahora conoce las proximas tres políticas "
					"en el mazo. El Presidente puede compartir "
					"(o mentir al respecto!) los resultados de su "
					"investigación a su propia discreción." % game.board.state.president.name)
				game.history.append("El presidente %s ahora conoce las proximas 3 políticas en el mazo." % game.board.state.president.name)
				action_policy(bot, game)                
			elif action == "kill":
				msg = "Poder Presidencial habilitado: Ejecución " + u"\U0001F5E1" + "\nEl Presidente %s tiene que matar a ua persona. Pueden discutir la desición ahora pero el Presidente tiene la última palabra." % game.board.state.president.name
				bot.send_message(game.cid, msg)
				game.board.state.fase = "legislating power kill"
				Commands.save_game(game.cid, "legislating power kill Round %d" % (game.board.state.currentround), game)
				action_kill(bot, game)				
			elif action == "inspect":
				bot.send_message(game.cid,
					"Poder Presidencial habilitado: Investigar Afiliación Política " + u"\U0001F50E" + "\nEl Presidente %s puede ver la afiliación política de un "
					"jugador. El Presidente puede compartir "
					"(o mentir al respecto!) los resultados de su "
					"investigación a su propia discreción." % game.board.state.president.name)
				game.board.state.fase = "legislating power inspect"
				Commands.save_game(game.cid, "legislating power inspect Round %d" % (game.board.state.currentround), game)				
				action_inspect(bot, game)
			elif action == "choose":
				bot.send_message(game.cid,
					"Poder Presidencial habilitado: Llamar a Elección Especial " + u"\U0001F454" + "\nEl Presidente %s puede elegir al próximo candidato presidencial. "
					"Despúes el orden continua "
					"normalmente." % game.board.state.president.name)
				game.board.state.fase = "legislating power choose"
				Commands.save_game(game.cid, "legislating power choose Round %d" % (game.board.state.currentround), game)
				action_choose(bot, game)
		else:
			start_next_round(bot, game)
	else:
		start_next_round(bot, game)


def choose_veto(update: Update, context: CallbackContext):
	
    bot = context.bot

    callback = update.callback_query
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        game = Commands.get_game(cid)
        uid = callback.from_user.id
        if answer == "yesveto":
            log.info("Player %s (%d) accepted the veto" % (callback.from_user.first_name, uid))
            bot.edit_message_text("Has aceptado el Veto!", uid, callback.message.message_id)
            bot.send_message(game.cid,
                             "El Presidente %s ha aceptado el Veto del Canciller %s. No se ha promulgado una politíca pero esto cuenta como una elección fallida." % (
                                 game.board.state.president.name, game.board.state.chancellor.name))
            game.board.discards += game.board.state.drawn_policies
            game.board.state.drawn_policies = []
            game.board.state.failed_votes += 1
            shuffle_policy_pile(bot, game)  
            if game.board.state.failed_votes == 3:
                do_anarchy(bot, game)
            else:                
                start_next_round(bot, game)
        elif answer == "noveto":
            log.info("Player %s (%d) declined the veto" % (callback.from_user.first_name, uid))
            game.board.state.veto_refused = True
            bot.edit_message_text("Has rechazado el Veto!", uid, callback.message.message_id)
            bot.send_message(game.cid,
                             "El Presidente %s ha rechazado el Veto del Canciller %s. El Canciller debe ahora elegir una política!" % (
                                 game.board.state.president.name, game.board.state.chancellor.name))
            pass_two_policies(bot, game)
        else:
            log.error("choose_veto: Callback data can either be \"veto\" or \"noveto\", but not %s" % answer)
    except:
        log.error("choose_veto: Game or board should not be None!")


def do_anarchy(bot, game):
	#log.info('do_anarchy called')	
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
                     "Las próximas 3 politicas son (La de arriba es la primera):\n%s\nPuedes mentir al respectosi quieres." % topPolicies)
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
	Commands.print_board(bot, game, game.board.state.president.uid)
	bot.send_message(game.board.state.president.uid,
		'Tienes que matar a una persona. Puedes discutir tu decisión con los otros. Elige sabiamente!',
		reply_markup=killMarkup)


def choose_kill(update: Update, context: CallbackContext):
	
    bot = context.bot
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_kill_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = int(regex.group(2))
    try:
        game = Commands.get_game(cid)
        chosen = game.playerlist[answer]
        chosen.is_dead = True
        if game.player_sequence.index(chosen) <= game.board.state.player_counter:
            game.board.state.player_counter -= 1
        game.player_sequence.remove(chosen)
        game.board.state.dead += 1
        log.info("El jugador %s (%d) mató a %s (%d)" % (
            callback.from_user.first_name, callback.from_user.id, chosen.name, chosen.uid))
        bot.edit_message_text("Has matado a %s!" % chosen.name, callback.from_user.id, callback.message.message_id)
        if chosen.role == "Hitler":
            bot.send_message(game.cid, "El Presidente " + game.board.state.president.name + " ha matado a " + chosen.name + ". ")
            end_game(bot, game, 2)
        else:
            bot.send_message(game.cid,
                             "El Presidente %s ha matado a %s que no era Hitler. %s, ahora estás muerto y no puedes hablar más!" % (
                                 game.board.state.president.name, chosen.name, chosen.name))
            
            game.history.append("El Presidente %s ha matado a %s que no era Hitler!" % (game.board.state.president.name, chosen.name))
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
    Commands.print_board(bot, game, game.board.state.president.uid)
    bot.send_message(game.board.state.president.uid,
                     'Puedes elegir al próximo candidato a presidente. Después el orden vuelve a la normalidad. Elige sabiamente!',
                     reply_markup=inspectMarkup)


def choose_choose(update: Update, context: CallbackContext):
	
    bot = context.bot
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_choo_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = int(regex.group(2))
    try:
        game = Commands.get_game(cid)
        chosen = game.playerlist[answer]
        game.board.state.chosen_president = chosen
        log.info(
            "El jugador %s (%d) ha elegido a %s (%d) como próximo Presidente" % (
                callback.from_user.first_name, callback.from_user.id, chosen.name, chosen.uid))
        bot.edit_message_text("Has elegido a %s como el próximo presidente!" % chosen.name, callback.from_user.id,
                              callback.message.message_id)
        bot.send_message(game.cid,
                         "El Presidente %s ha elegido a %s como próximo presidente." % (
                             game.board.state.president.name, chosen.name))
        game.history.append("El Presidente %s ha elegido a %s como próximo presidente." % (game.board.state.president.name, chosen.name))
        start_next_round(bot, game)
    except:
        log.error("choose_choose: Game or board should not be None!")


def action_inspect(bot, game):
    log.info('action_inspect called')
    strcid = str(game.cid)
    btns = []
    for uid in game.playerlist:
        if uid != game.board.state.president.uid and game.playerlist[uid].is_dead == False and game.playerlist[uid].was_investigated == False:
            name = game.playerlist[uid].name
            btns.append([InlineKeyboardButton(name, callback_data=strcid + "_insp_" + str(uid))])

    inspectMarkup = InlineKeyboardMarkup(btns)
    Commands.print_board(bot, game, game.board.state.president.uid)
    bot.send_message(game.board.state.president.uid,
                     'Puedes ver la afiliación política de un jugador. A quien quieres elegir? Elige sabiamente!',
                     reply_markup=inspectMarkup)


def choose_inspect(update: Update, context: CallbackContext):
	
    bot = context.bot
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_insp_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = int(regex.group(2))
    try:
        game = Commands.get_game(cid)
        chosen = game.playerlist[answer]
        log.info(
            "Player %s (%d) inspects %s (%d)'s party membership (%s)" % (
                callback.from_user.first_name, callback.from_user.id, chosen.name, chosen.uid,
                chosen.party))
        bot.edit_message_text("La afiliación política de %s es %s" % (chosen.name, chosen.party),
                              callback.from_user.id,
                              callback.message.message_id)
        chosen.was_investigated = True
        bot.send_message(game.cid, "El Presidente %s ha inspeccionado a %s." % (game.board.state.president.name, chosen.name))
        game.history.append("El Presidente %s ha inspeccionado a %s." % (game.board.state.president.name, chosen.name))
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


def decide_anarquia(bot, game):
	log.info('decide_anarquia called')
	#When voting starts we start the counter to see later with the vote command if we can see you voted.
	game.board.state.votes_anarquia = {}
	strcid = str(game.cid)
	btns = [[InlineKeyboardButton("Ja", callback_data=strcid + "_SiAna"),
	InlineKeyboardButton("Nein", callback_data=strcid + "_NoAna")]]
	voteMarkup = InlineKeyboardMarkup(btns)
	for uid in game.playerlist:
		if not game.is_debugging:
			if not game.playerlist[uid].is_dead:                      
				Commands.print_board(bot, game, uid)				
				bot.send_message(uid, "¿Quieres ir a anarquia? (CUIDADO si la mitad de los jugadores elige SI no se espera)", reply_markup=voteMarkup)
		else:
			bot.send_message(ADMIN, game.board.print_board(game.player_sequence))
			bot.send_message(ADMIN, "¿Quieres ir a anarquia? (CUIDADO si la mitad de los jugadores elige SI no se espera)", reply_markup=voteMarkup)
			
def handle_voting_anarquia(update: Update, context: CallbackContext):
	bot = context.bot
	callback = update.callback_query
	log.info('handle_voting_anarquia called: %s' % callback.data)
	regex = re.search("(-[0-9]*)_(.*)", callback.data)
	cid = int(regex.group(1))
	answer = regex.group(2)
	strcid = regex.group(1)
	try:
		game = Commands.get_game(cid)
		uid = callback.from_user.id
		answer = answer.replace("Ana", "")
		bot.edit_message_text("Gracias por tu voto: %s para la anarquia" % (answer), uid, callback.message.message_id)
		log.info("Player %s (%d) voted %s" % (callback.from_user.first_name, uid, answer))

		#if uid not in game.board.state.last_votes:
		game.board.state.votes_anarquia[uid] = answer
		
		if game.is_debugging:
			for uid in game.playerlist:
				if not game.playerlist[uid].is_dead:
					game.board.state.votes_anarquia[uid] = answer			

		#Allow player to change his vote
		btns = [[InlineKeyboardButton("Ja", callback_data=strcid + "_JaAna"),
		InlineKeyboardButton("Nein", callback_data=strcid + "_NeinAna")]]
		voteMarkup = InlineKeyboardMarkup(btns)
		bot.send_message(uid, "Puedes cambiar tu voto aquí.\n¿Quieres ir a anarquia? (CUIDADO si la mitad de los jugadores elige SI no se espera)", reply_markup=voteMarkup)
		
		if len(game.board.state.votes_anarquia) == len(game.player_sequence):
			count_votes_anarquia(bot, game)
		'''elif list(game.board.state.votes_anarquia.values()).count("Si") >= (len(game.player_sequence) / 2):
			# Caso especial si ya la mitad o mas de los jugadores decidio ir a anarquia se va no más.
			count_votes_anarquia(bot, game)
		'''
	except Exception as e:
		log.error(str(e))

def count_votes_anarquia(bot, game):
	# La votacion ha finalizado.
	game.dateinitvote = None
	# La votacion ha finalizado.
	log.info('count_votes_anarquia called')
	voting_text = ""
	voting_success = False
	for player in game.player_sequence:
		nombre_jugador = game.playerlist[player.uid].name
		if game.board.state.votes_anarquia[player.uid] == "Si":
			voting_text += nombre_jugador + " votó Ja!\n"
		elif game.board.state.votes_anarquia[player.uid] == "No":
			voting_text += nombre_jugador + " votó Nein!\n"
	if list(game.board.state.votes_anarquia.values()).count("Si") >= (len(game.player_sequence) / 2):  # because player_sequence doesnt include dead
		# VOTING WAS SUCCESSFUL
		log.info("Vamos a anarquia!")
		voting_text += "Debido a que la mayoria de los jugador ha decidido ir a anarquia se ejecuta la anarquia."		
		game.board.state.nominated_president = None
		game.board.state.nominated_chancellor = None
		bot.send_message(game.cid, voting_text, ParseMode.MARKDOWN)
		bot.send_message(game.cid, "\nNo se puede hablar ahora.")
		game.history.append(("Ronda %d.%d\n\n" % (game.board.state.liberal_track + game.board.state.fascist_track + 1, game.board.state.failed_votes + 1) ) + voting_text)
		# Avanzo la cantidad del lider asi el lider queda correctamente asignado
		# Se incrementa como mucho 2 ya que el ultimo incremento lo hace la anarquia
		for i in range(2 - game.board.state.failed_votes):
			increment_player_counter(game)		
		do_anarchy(bot, game)
	else:
		log.info("La gente no quiere anarquia")
		voting_text += "Al no quiso ir a anarquia"
		game.board.state.nominated_president = None
		game.board.state.nominated_chancellor = None
		bot.send_message(game.cid, voting_text, ParseMode.MARKDOWN)
		game.history.append(("Ronda %d.%d\n\n" % (game.board.state.liberal_track + game.board.state.fascist_track + 1, game.board.state.failed_votes + 1) ) + voting_text)
		#game.board.state.failed_votes == 3
		
			
##
#
# End of round
#
##

def get_stats(bot, cid):
	try:
		cur = conn.cursor()
		query = "select * from stats"
		cur.execute(query)
		dbdata = cur.fetchone()
		return dbdata
	except Exception as e:
		bot.send_message(cid, 'No se ejecuto el comando get_stats debido a: '+str(e))
		conn.rollback()	

def set_stats(column_name, value, bot, cid):
	try:
		cursor = conn.cursor()
		#cursor.execute("UPDATE stats SET %s=%s", (column_name, value));		
		cursor.execute(sql.SQL("UPDATE stats set {}=%s ").format(sql.Identifier(column_name)), [value])
		
		conn.commit()
	except Exception as e:
		bot.send_message(cid, 'No se ejecuto el comandoset_stats debido a: '+str(e))
		conn.rollback()
		
def save_game_details(bot, print_roles, game_endcode, liberal_track, fascist_track, num_players):
	try:
		#Check if game is in DB first
		cursor = conn.cursor()			
		log.info("Executing in DB")		
		query = "INSERT INTO stats_detail(playerlist, game_endcode, liberal_track, fascist_track, num_players) VALUES (%s, %s, %s, %s, %s);"
		#query = "INSERT INTO games(id , groupName  , data) VALUES (%s, %s, %s) RETURNING data;"
		cursor.execute(query, (print_roles, game_endcode, liberal_track, fascist_track, num_players))		
		#dbdata = cur.fetchone()
		conn.commit()
	except Exception as e:
		conn.rollback()
		bot.send_message(ADMIN, 'No se ejecuto el comando save_game_details debido a: '+str(e))

def change_stats(uid, tipo_juego, stat_name, amount):
	user_stats = load_player_stats(uid)		
	# Si no tiene registro, lo creo
	if user_stats is None:
		user_stats = PlayerStats(uid)	
	user_stats.change_data_stat(tipo_juego, stat_name, amount)
	save_player_stats(uid, user_stats)	

def save_player_stats(uid, data):
	#Check if game is in DB first
	cur = conn.cursor()			
	log.info("Searching Game in DB")
	query = "select * from user_stats where id = %s;"
	cur.execute(query, [uid])
	#dbdata = cur.fetchone()
	if cur.rowcount > 0:
		log.info('Updating user_stats')
		datajson = jsonpickle.encode(data)
		#query = "UPDATE games SET groupName = %s, data = %s WHERE id = %s RETURNING data;"
		query = "UPDATE user_stats SET data = %s WHERE id = %s;"
		cur.execute(query, (datajson, uid))
		#log.info(cur.fetchone()[0])
		conn.commit()		
	else:
		log.info('Saving user_stats in DB')
		datajson = jsonpickle.encode(data)
		query = "INSERT INTO user_stats(id, data) VALUES (%s, %s);"
		#query = "INSERT INTO games(id , groupName  , data) VALUES (%s, %s, %s) RETURNING data;"
		cur.execute(query, (uid, datajson))
		#log.info(cur.fetchone()[0])
		conn.commit()

def load_player_stats(uid):
	cur = conn.cursor()			
	log.info("Searching Game in DB")
	query = "SELECT * FROM user_stats WHERE id = %s;"
	cur.execute(query, [uid])
	dbdata = cur.fetchone()

	if cur.rowcount > 0:
		log.info("user_stats Found")
		jsdata = dbdata[1]
		log.info("jsdata = {}".format(jsdata))				
		stats = jsonpickle.decode(jsdata)
		return stats
	else:
		log.info("user_stats Not Found")
		return None

##
# game_endcode:
#   -2  fascists win by electing Hitler as chancellor
#   -1  fascists win with 6 fascist policies
#   0   not ended
#   1   liberals win with 5 liberal policies
#   2   liberals win by killing Hitler
#   99  game cancelled
#		
def end_game(bot, game, game_endcode):
	log.info('end_game called')
	cid = game.cid
	
	# Grabo detalles de la partida
	if game_endcode != 99:
		save_game_details(bot, game.print_roles(), game_endcode, game.board.state.liberal_track, game.board.state.fascist_track, game.board.num_players)
	
	
	#bot.send_message(cid, "Datos a guardar %s %s %s %s %s" % (game.print_roles(), str(game_endcode), str(game.board.state.liberal_track), str(game.board.state.fascist_track), str(game.board.num_players)))
		
	stats = get_stats(bot, cid)	
	if game_endcode == 99:
		if GamesController.games[cid].board is not None:
			bot.send_message(cid, "Juego cancelado!\n\n%s" % game.print_roles())
		else:
			bot.send_message(cid, "Juego cancelado!")
		set_stats("cancelgame", stats[5] + 1, bot, cid)
	else:
		if game_endcode == -2:
			bot.send_message(game.cid, "Juego finalizado! Los fascistas ganaron eligiendo a Hitler como Canciller!\n\n%s" % game.print_roles())
			set_stats("fascistwinhitler", stats[1] + 1, bot, cid)
		if game_endcode == -1:
			bot.send_message(game.cid, "Juego finalizado! Los fascistas ganaron promulgando 6 políticas fascistas!\n\n%s" % game.print_roles())
			set_stats("fascistwinpolicies", stats[2] + 1, bot, cid)
		if game_endcode == 1:
			bot.send_message(game.cid, "Juego finalizado! Los liberales ganaron promulgando 5 políticas liberales!\n\n%s" % game.print_roles())
			set_stats("liberalwinpolicies", stats[3] + 1, bot, cid)
		if game_endcode == 2:
			bot.send_message(game.cid, "Juego finalizado! Los liberales ganaron matando a Hitler!\n\n%s" % game.print_roles())
			set_stats("liberalwinkillhitler", stats[4] + 1, bot, cid)
		showHiddenhistory(bot, game)
	del GamesController.games[cid]
	Commands.delete_game(cid)
	
def showHiddenhistory(bot, game):
	#game.pedrote = 3
	try:
		#Check if there is a current game
		history_text = "Historial Oculto:\n\n" 
		for x in game.hiddenhistory:				
			history_text += x + "\n"
		bot.send_message(game.cid, history_text, ParseMode.MARKDOWN)
	except Exception as e:
		bot.send_message(game.cid, str(e))
		log.error("Unknown error: " + str(e)) 
        
def inform_players(bot, game, cid, player_number):
	log.info('inform_players called')
	bot.send_message(cid,
		"Vamos a comenzar el juego con %d jugadores!\n%s\nVe a nuestro chat privado y mira tu rol secreto!" % (
		player_number, print_player_info(player_number)))
	available_roles = list(playerSets[player_number]["roles"])  # copy not reference because we need it again later
	# Mezclo los roles asi si alguien elije Fascista o Hitler no le toca siempre Fascista
	random.shuffle(available_roles)
	# Creo una lista unica para poder repartir los roles a partir de las key de los player list
	player_ids = list(game.playerlist.keys())
	# Lo mezclo y lo uso para pasar por todos los jugadores
	random.shuffle(player_ids)
	
	for uid in player_ids:
		# Antes de buscar un rol en particular pregunto si el jugador queria ser algo en particular
		preferencia_jugador = game.playerlist[uid].preference_rol		
		# Si el jugador tiene una preferencia... defecto se pone "" y daria [''] como preferencias		
		preferencias = preferencia_jugador.split('_')
		# El primer rol que aparece de las preferencias del jugador, devuelve None si no hay
		indice_preferencia = next((i for i,v in enumerate(available_roles) if v in preferencias), -1)
		
		# Si el jugador tiene una preferencia se le asigna esta, como el orden es random no se sabe si se sabe si se
		# cumplirá esto ya que los roles pudieron haber sido tomados ya.		
		if indice_preferencia == -1:
			#print "No hay indices de la preferencia"
			random_index = random.randrange(len(available_roles))
		else:
			random_index = indice_preferencia
			
		#log.info(str(random_index))
		role = available_roles.pop(random_index)
		#log.info(str(role))
		party = get_membership(role)
		game.playerlist[uid].role = role
		game.playerlist[uid].party = party
		
		# I comment so tyhe player aren't discturbed in testing, uncomment when deploy to production
		if not game.is_debugging:
			bot.send_message(uid, "Tu rol secreto es: %s\nTu afiliación política es: %s" % (role, party))
		else:
			bot.send_message(ADMIN, "El jugador %s es %s y su afiliación política es: %s" % (game.playerlist[uid].name, role, party))


def print_player_info(player_number):
    if player_number == 5:
        return "Hay 3 Liberales, 1 Fascista y Hitler. Hitler conoce quien es el Fascista."
    elif player_number == 6:
        return "Hay  4 Liberales, 1 Fascista y Hitler. Hitler conocer quienes quien es el Fascista."
    elif player_number == 7:
        return "Hay  4 Liberales, 2 Fascistas y Hitler. Hitler no conoce quienes son los Fascistas."
    elif player_number == 8:
        return "Hay  5 Liberales, 2 Fascistas y Hitler. Hitler no conoce quienes son los Fascistas."
    elif player_number == 9:
        return "Hay  5 Liberales, 3 Fascistas y Hitler. Hitler no conoce quienes son los Fascistas."
    elif player_number == 10:
        return "Hay  6 Liberales, 3 Fascistas y Hitler. Hitler no conoce quienes son los Fascistas."


def inform_fascists(bot, game, player_number):
	log.info('inform_fascists called')

	for uid in game.playerlist:
		role = game.playerlist[uid].role
		if role == "Fascista":
			fascists = game.get_fascists()
			if player_number > 6:
				fstring = ""
				for f in fascists:
					if f.uid != uid:
						fstring += f.name + ", "
				fstring = fstring[:-2]
				if not game.is_debugging:
					bot.send_message(uid, "Tus compañeros fascistas son: %s" % fstring)
			hitler = game.get_hitler()
			if not game.is_debugging:
				bot.send_message(uid, "Hitler es: %s" % hitler.name) #Uncoomend on production
		elif role == "Hitler":
			if player_number <= 6:
				fascists = game.get_fascists()
				if not game.is_debugging:
					bot.send_message(uid, "Tu compañero fascista es: %s" % fascists[0].name)
		elif role == "Liberal":
			pass
		else:
			log.error("inform_fascists: can\'t handle the role %s" % role)


def get_membership(role):
    log.info('get_membership called')
    if role == "Fascista" or role == "Hitler":
        return "fascista"
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
		game.history.append("*No habia cartas suficientes en el mazo de políticas asi que he mezclado el resto con el mazo de descarte!*")
		game.hiddenhistory.append("*No habia cartas suficientes en el mazo de políticas asi que he mezclado el resto con el mazo de descarte!*")
		game.board.discards += game.board.policies
		game.board.policies = random.sample(game.board.discards, len(game.board.discards))
		game.board.discards = []		
		bot.send_message(game.cid,
			"No habia cartas suficientes en el mazo de políticas asi que he mezclado el resto con el mazo de descarte!")

def getGamesByTipo(opcion):
	games = None
	cursor = conn.cursor()			
	log.info("Executing in DB")
	if opcion != "Todos":
		query = "select * from games g where g.tipojuego = '{0}'".format(opcion)
	else:
		query = "select * from games g"
	
	cursor.execute(query)
	if cursor.rowcount > 0:
		# Si encuentro juegos los busco a todos y los cargo en memoria
		for table in cursor.fetchall():
			if table[0] not in GamesController.games.keys():
				Commands.get_game(table[0])
		# En el futuro hacer que pueda hacer anuncios globales a todos los juegos ?
		games_restriction = [opcion]
		#bot.send_message(uid, "Obtuvo esta cantidad de juegos: {0}".format(len(GamesController.games)))
		# Luego aplico
		if opcion != "Todos":
			games = {key:val for key, val in GamesController.games.items() if val.tipo in games_restriction}
		else:
			games = GamesController.games		
	return games

def error_callback(update, context):
	# add all the dev user_ids in this list. You can also add ids of channels or groups.
	devs = [ADMIN]    
	# This traceback is created with accessing the traceback object from the sys.exc_info, which is returned as the
	# third value of the returned tuple. Then we use the traceback.format_tb to get the traceback as a string, which
	# for a weird reason separates the line breaks in a list, but keeps the linebreaks itself. So just joining an
	# empty string works fine.
	trace = "".join(traceback.format_tb(sys.exc_info()[2]))
	# lets try to get as much information from the telegram update as possible
	payload = ""
	# normally, we always have an user. If not, its either a channel or a poll update.
	if update.effective_user:
		payload += f' with the user {mention_html(update.effective_user.id, update.effective_user.first_name)}'
	# there are more situations when you don't get a chat
	if update.effective_chat:
		payload += f' within the chat <i>{update.effective_chat.title}</i>'
	if update.effective_chat.username:
		payload += f' (@{update.effective_chat.username})'
	# but only one where you have an empty payload by now: A poll (buuuh)
	if update.poll:
		payload += f' with the poll id {update.poll.id}.'
	# lets put this in a "well" formatted text
	text = f"Hey.\n The error <code>{context.error}</code> happened{payload}. The full traceback:\n\n<code>{trace}" \
	f"</code>"
	# and send it to the dev(s)
	for dev_id in devs:
		context.bot.send_message(dev_id, text, parse_mode=ParseMode.HTML)
	# we raise the error again, so the logger module catches it. If you don't use the logger module, use it.
	logger.warning("User: {}.\n\nError {}.\n\nTrace: {}".format(update.effective_user.first_name, context.error, trace))
	
def change_groupname(bot, update):
	cid = update.message.chat.id
	groupname = update.message.chat.title
	game = Commands.get_game(cid)
	game.groupName = groupname
	bot.send_message(ADMIN, text="El group en {cid} ha cambiado de nombre a {groupname}".format(groupname=groupname, cid=cid))

def get_TOKEN():	
	cur = conn.cursor()
	query = "select * from config;"
	cur.execute(query)
	dbdata = cur.fetchone()
	token = dbdata[1]
	return token
	
def main():
	GamesController.init() #Call only once

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

	# polling
	'''
	updater = Updater(get_TOKEN())
	'''
	# Pruebas de HOOKS
	token = os.environ.get('bot_token', None)
	PORT = int(os.environ.get('PORT', '8443'))
	updater = Updater(token, use_context=True)
	
	# Lo de abajo se usa para web deploy son web hooks
	'''
	updater.start_webhook(listen="0.0.0.0",
                      port=PORT,
                      url_path=token)
	updater.bot.set_webhook("https://secrethitler.herokuapp.com/{0}".format(token))
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
	dp.add_handler(CommandHandler("join", Commands.command_join))
	dp.add_handler(CommandHandler("history", Commands.command_showhistory))
	dp.add_handler(CommandHandler("votes", Commands.command_votes))
	dp.add_handler(CommandHandler("calltovote", Commands.command_calltovote))	
	dp.add_handler(CommandHandler("claim", Commands.command_claim))
	dp.add_handler(CommandHandler("reload", Commands.command_reloadgame))
	dp.add_handler(CommandHandler("debug", Commands.command_toggle_debugging))
	dp.add_handler(CommandHandler("anarchy", Commands.command_anarquia))
	dp.add_handler(CommandHandler("prueba", Commands.command_prueba))
	dp.add_handler(CommandHandler("claimoculto", Commands.command_claim_oculto))
	dp.add_handler(CommandHandler("info", Commands.command_info))
	dp.add_handler(CallbackQueryHandler(pattern=r"(-?[0-9]*)\*chooseGameInfo\*(.*)\*(-?[0-9]*)", callback=Commands.callback_info))
	dp.add_handler(CommandHandler("jugadores", Commands.command_jugadores))

	#Testing commands
	dp.add_handler(CommandHandler("ja", Commands.command_ja))
	dp.add_handler(CommandHandler("nein", Commands.command_nein))

	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_chan_(.*)", callback=nominate_chosen_chancellor))
	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_insp_(.*)", callback=choose_inspect))
	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_choo_(.*)", callback=choose_choose))
	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_kill_(.*)", callback=choose_kill))
	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(yesveto|noveto)", callback=choose_veto))
	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(liberal|fascista|veto)", callback=choose_policy))
	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(Ja|Nein)", callback=handle_voting))
	dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(SiAna|NoAna)", callback=handle_voting_anarquia))
	
	dp.add_handler(CommandHandler("comando", Commands.command_newgame_sql_command))
	
	# Comandos para elegir rol al unirse a la partida
	dp.add_handler(CommandHandler("role", Commands.command_choose_posible_role))
	dp.add_handler(CallbackQueryHandler(pattern=r"(-[0-9]*)\*chooserole\*(.*)\*([0-9]*)", callback=Commands.callback_choose_posible_role))

	dp.add_handler(CommandHandler("showstats", Commands.command_show_stats))
	dp.add_handler(CommandHandler("changestats", Commands.command_change_stats))

	dp.add_handler(MessageHandler(Filters.status_update.new_chat_title, change_groupname))
	
	# log all errors
	dp.add_error_handler(error_callback)
	
	# Comentar linea de abajo si se quiere usar web deploy
	updater.start_polling(timeout=30)
	
	# pruebas de hooks
	updater.idle()
	
	'''
	# Start the Bot
	updater.start_polling()
	# Run the bot until the you presses Ctrl-C or the process receives SIGINT,
	# SIGTERM or SIGABRT. This should be used most of the time, since
	# start_polling() is non-blocking and will stop the bot gracefully.
	updater.idle()
	'''


if __name__ == '__main__':
    main()

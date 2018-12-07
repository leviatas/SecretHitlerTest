import json
import logging as log
import datetime
#import ast
import jsonpickle
import os
import psycopg2
import urllib.parse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode

import MainController
import GamesController
import re

from Constants.Config import STATS
from Constants.Config import ADMIN
from Constants.Cards import opciones_choose_posible_role

from Boardgamebox.Board import Board
from Boardgamebox.Game import Game
from Boardgamebox.Player import Player
from Boardgamebox.State import State

from collections import namedtuple

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

commands = [  # command description used in the "help" command
    '/help - Te da informacion de los comandos disponibles',
    '/start - Da un poco de información sobre Secret Hitler',
    '/symbols - Te muestra todos los símbolos posibles en el tablero',
    '/rules - Te da un link al sitio oficial con las reglas de Secret Hitler',
    '/newgame - Crea un nuevo juego o carga un juego previo',
    '/join - Te une a un juego existente',
    '/startgame - Comienza un juego existente cuando todos los jugadores se han unido',
    '/cancelgame - Cancela un juego existente, todos los datos son borrados.',
    '/board - Imprime el tablero actual con la pista liberal y la pista fascista, orden presidencial y contador de elección',
    '/history - Imprime el historial del juego actual',
    '/votes - Imprime quien ha votado',
    '/calltovote - Avisa a los jugadores que se tiene que votar'    
]

symbols = [
    u"\u25FB\uFE0F" + ' Lugar vacio sin poder especial',
    u"\u2716\uFE0F" + ' Campo cubierto con una carta',  # X
    u"\U0001F52E" + ' Poder Presidencial: Investigar Políticas',  # crystal
    u"\U0001F50E" + ' Poder Presidencial: Investigar Afiliación Política',  # inspection glass
    u"\U0001F5E1" + ' Poder Presidencial: Ejecución',  # knife
    u"\U0001F454" + ' Poder Presidencial: Llamar a Elección Especial',  # tie
    u"\U0001F54A" + ' Liberales ganan',  # dove
    u"\u2620" + ' Fascistas ganan'  # skull
]

def get_game(cid):
	# Busco el juego actual
	game = GamesController.games.get(cid, None)	
	if game:
		# Si esta lo devuelvo.
		return game
	else:
		# Si no esta lo busco en BD y lo pongo en GamesController.games
		game = load_game(cid)
		if game:
			GamesController.games[cid] = game
			return game
		else:
			None

def command_symbols(bot, update):
    cid = update.message.chat_id
    symbol_text = "Los siguientes símbolos aparecen en el tablero: \n"
    for i in symbols:
        symbol_text += i + "\n"
    bot.send_message(cid, symbol_text)


def command_board(bot, update):
	cid = update.message.chat_id
	game = get_game(cid)
	if game:		
		if game.board:			
			print_board(bot, game, cid)
		else:
			bot.send_message(cid, "No hay juego comenzado en este chat.  Por favor comience el juego con /startgame")
	else:
		bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")

def print_board(bot, game, target):
	bot.send_message(target, game.board.print_board(game.player_sequence), ParseMode.MARKDOWN)
		
def command_start(bot, update):
	cid = update.message.chat_id
	bot.send_message(cid,
		     "\"Secret Hitler es un juego de deducción social para 5-10 jugadores "
		     "acerca de encontrar a Hitler y detener el ascenso del fascismo."
		     " La mayoría de los jugadores son liberales. Si pueden aprender a "
		     "confiar entre ellos, tienen suficientes votos para controlar el parlamento y ganar el juego."
		     " Pero algunos jugadores son fascistas. Ellos dirán lo que sea necesario para ser electos, "
		     "promover el fascismo y culpar a los demás por la derrota de la República."
		     " Los liberales deben trabajar juntos para descubrir la verdad antes "
		     "de que los fascistas instalen a su desalamado líder y ganen el juego."
		     " Traducción de la descripición oficial de Secret Hitler."
		     " Agregame a un grupo y escribe /newgame para crear un juego!")
	command_help(bot, update)


def command_rules(bot, update):
    cid = update.message.chat_id
    btn = [[InlineKeyboardButton("Rules", url="http://www.secrethitler.com/assets/Secret_Hitler_Rules.pdf")]]
    rulesMarkup = InlineKeyboardMarkup(btn)
    bot.send_message(cid, "Lee las reglas oficiales de Secret Hitler:", reply_markup=rulesMarkup)


# pings the bot
def command_ping(bot, update):
    cid = update.message.chat_id
    bot.send_message(cid, 'pong - v0.3')


# prints statistics, only ADMIN
def command_stats(bot, update):
	cid, uid = update.message.chat_id, update.message.from_user.id
	if ADMIN == ADMIN:
		stats = MainController.get_stats(bot, cid)		
		stattext = "+++ Estadísticas +++\n" + \
				"Vict. Liberal (Politicas): *" + str(stats[3]) + "*\n" + \
				"Vict. Liberal (Hitler ☠): *" + str(stats[4]) + "*\n" + \
				"Vict. Fascista (Politicas): *" + str(stats[2]) + "*\n" + \
				"Vict. Fascista (Hitler Canc): *" + str(stats[1]) + "*\n" + \
				"Juegos cancelados: *" + str(stats[5]) + "*\n" + \
				"Juegos totales: *" + str(stats[1] + stats[2] + stats[3] + stats[4]) + "*\n\n"		
		bot.send_message(cid, stattext, ParseMode.MARKDOWN)
		
# help page
def command_help(bot, update):
    cid = update.message.chat_id
    help_text = "Los siguientes comandos están disponibles:\n"
    for i in commands:
        help_text += i + "\n"
    bot.send_message(cid, help_text)

def command_newgame(bot, update):  
	cid = update.message.chat_id
		
	try:
		game = get_game(cid)
		groupType = update.message.chat.type
		if groupType not in ['group', 'supergroup']:
			bot.send_message(cid, "Tienes que agregarme a un grupo primero y escribir /newgame allá!")
		elif game:
			bot.send_message(cid, "Hay un juego comenzado en este chat. Si quieres terminarlo escribe /cancelgame!")
		else:
			GamesController.games[cid] = Game(cid, update.message.from_user.id)
			bot.send_message(cid, "Nuevo juego creado! Cada jugador debe unirse al juego con el comando /join.\nEl iniciador del juego (o el administrador) pueden unirse tambien y escribir /startgame cuando todos se hayan unido al juego!")
			
	except Exception as e:
		bot.send_message(cid, str(e))


def command_join(bot, update, args):
	# I use args for testing. // Remove after?
	groupName = update.message.chat.title
	cid = update.message.chat_id
	groupType = update.message.chat.type
	game = get_game(cid)
	if len(args) <= 0:
		# if not args, use normal behaviour
		fname = update.message.from_user.first_name.replace("_", " ")
		uid = update.message.from_user.id
	else:
		uid = update.message.from_user.id
		if uid == ADMIN:
			for i,k in zip(args[0::2], args[1::2]):
				fname = i.replace("_", " ")
				uid = int(k)
				player = Player(fname, uid)
				game.add_player(uid, player)
				log.info("%s (%d) joined a game in %d" % (fname, uid, game.cid))
				save_game(cid, "Game in join state", game)
	
	if groupType not in ['group', 'supergroup']:
		bot.send_message(cid, "Tienes que agregarme a un grupo primero y escribir /newgame allá!")
	elif not game:
		bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")
	elif game.board:
		bot.send_message(cid, "El juego ha comenzado. Por favor espera el proximo juego!")
	elif uid in game.playerlist:
		bot.send_message(game.cid, "Ya te has unido al juego, %s!" % fname)
	elif len(game.playerlist) >= 10:
		bot.send_message(game.cid, "Han llegado al maximo de jugadores. Por favor comiencen el juego con /startgame!")
	else:
		#uid = update.message.from_user.id
		player = Player(fname, uid)
		try:
			#Commented to dont disturb player during testing uncomment in production
			bot.send_message(uid, "Te has unido a un juego en %s. Pronto te dire cual es tu rol secreto." % groupName)
			choose_posible_role(bot, cid, uid)
			
			game.add_player(uid, player)
			log.info("%s (%d) joined a game in %d" % (fname, uid, game.cid))
			if len(game.playerlist) > 4:
				bot.send_message(game.cid, fname + " se ha unido al juego. Escribe /startgame si este es el último jugador y quieren comenzar con %d jugadores!" % len(game.playerlist))
			elif len(game.playerlist) == 1:
				bot.send_message(game.cid, "%s se ha unido al juego. Hay %d jugador en el juego y se necesita 5-10 jugadores." % (fname, len(game.playerlist)))
			else:
				bot.send_message(game.cid, "%s se ha unido al juego. Hay %d jugadores en el juego y se necesita 5-10 jugadores" % (fname, len(game.playerlist)))
			# Luego dicto los jugadores que se han unido
			jugadoresActuales = "Los jugadores que se han unido al momento son:\n"
			for uid in game.playerlist:
				jugadoresActuales += "%s\n" % game.playerlist[uid].name
			bot.send_message(game.cid, jugadoresActuales)
			save_game(cid, "Game in join state", game)
		except Exception:
			bot.send_message(game.cid,
				fname + ", No te puedo enviar un mensaje privado. Por favor, ve a @secrethitlertestlbot y has pincha \"Start\".\nLuego necesitas escribir /join de nuevo.")


def command_startgame(bot, update):
	log.info('command_startgame called')
	groupName = update.message.chat.title
	cid = update.message.chat_id
	game = get_game(cid)
	if not game:
		bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")
	elif game.board:
		bot.send_message(cid, "El juego ya ha comenzado!")
	elif update.message.from_user.id != game.initiator and bot.getChatMember(cid, update.message.from_user.id).status not in ("administrator", "creator"):
		bot.send_message(game.cid, "Solo el creador del juego or el admisnitrador del grupo pueden comenzar el juego con /startgame")
	elif len(game.playerlist) < 5:
		bot.send_message(game.cid, "No hay suficientes jugadores (min. 5, max. 10). Uneté al juego con /join")
	else:
		player_number = len(game.playerlist)
		MainController.inform_players(bot, game, game.cid, player_number)
		MainController.inform_fascists(bot, game, player_number)
		game.board = Board(player_number, game)
		log.info(game.board)
		log.info("len(games) Command_startgame: " + str(len(GamesController.games)))
		game.shuffle_player_sequence()
		game.board.state.player_counter = 0
		#print_board(bot, game, cid)
		#group_name = update.message.chat.title
		#bot.send_message(ADMIN, "Game of Secret Hitler started in group %s (%d)" % (group_name, cid))		
		MainController.start_round(bot, game)
		#save_game(cid, groupName, game)

def command_cancelgame(bot, update):
	log.info('command_cancelgame called')
	cid = update.message.chat_id	
	#Always try to delete in DB
	
	game = get_game(cid)
	
	#delete_game(cid)
	if game:		
		status = bot.getChatMember(cid, update.message.from_user.id).status
		if update.message.from_user.id == game.initiator or status in ("administrator", "creator"):
			MainController.end_game(bot, game, 99)
		else:
			bot.send_message(cid, "Solo el creador del juego o el administrador del grupo pueden cancelar el juego con /cancelgame")
	else:
		bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")

def command_votes(bot, update):
	try:
		#Send message of executing command   
		cid = update.message.chat_id
		#bot.send_message(cid, "Looking for history...")
		#Check if there is a current game 
		game = get_game(cid)
		if game:			
			if not game.dateinitvote:
				# If date of init vote is null, then the voting didnt start          
				bot.send_message(cid, "La votación no ha comenzado todavia!")
			else:
				#If there is a time, compare it and send history of votes.
				start = game.dateinitvote
				stop = datetime.datetime.now()
				elapsed = stop - start
				if elapsed > datetime.timedelta(minutes=5):
					history_text = "Historial de votacion para el Presidente %s y Canciller %s:\n\n" % (game.board.state.nominated_president.name, game.board.state.nominated_chancellor.name)
					for player in game.player_sequence:
						# If the player is in the last_votes (He voted), mark him as he registered a vote
						if player.uid in game.board.state.last_votes:
							history_text += "%s ha votado.\n" % (game.playerlist[player.uid].name)
						else:
							history_text += "%s *no* ha votado.\n" % (game.playerlist[player.uid].name)
					bot.send_message(cid, history_text, ParseMode.MARKDOWN)
				else:
					bot.send_message(cid, "Cinco minutos deben pasar para ver los votos") 
		else:
			bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")
	except Exception as e:
		bot.send_message(cid, str(e))

def command_calltovote(bot, update):
	try:
		#Send message of executing command   
		cid = update.message.chat_id
		#bot.send_message(cid, "Looking for history...")
		#Check if there is a current game 
		game = get_game(cid)
		if game:			
			if not game.dateinitvote:
				# If date of init vote is null, then the voting didnt start          
				bot.send_message(cid, "La votación no ha comenzado todavia!")
			else:
				#If there is a time, compare it and send history of votes.
				start = game.dateinitvote
				stop = datetime.datetime.now()          
				elapsed = stop - start
				if elapsed > datetime.timedelta(minutes=1):
					# Only remember to vote to players that are still in the game
					history_text = ""
					for player in game.player_sequence:
						# If the player is not in last_votes send him reminder
						if player.uid not in game.board.state.last_votes:
							history_text += "Es hora de votar [%s](tg://user?id=%d)!\n" % (game.playerlist[player.uid].name, player.uid)
					bot.send_message(cid, text=history_text, parse_mode=ParseMode.MARKDOWN)
				else:
					bot.send_message(cid, "Cinco minutos deben pasar para pedir que se vote!") 
		else:
			bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")
	except Exception as e:
		bot.send_message(cid, str(e))
        
def command_showhistory(bot, update):
	#game.pedrote = 3
	try:
		#Send message of executing command   
		cid = update.message.chat_id
		#Check if there is a current game 
		game = get_game(cid)
		if game:			
			#bot.send_message(cid, "Current round: " + str(game.board.state.currentround + 1))
			uid = update.message.from_user.id
			history_text = "Historial:\n\n" 
			history_textContinue = "" 
			for x in game.history:
				if len(history_text) < 3500:
					history_text += x + "\n\n"
				else:
					history_textContinue += x + "\n\n"

			bot.send_message(uid, history_text, ParseMode.MARKDOWN)
			if len(history_textContinue) > 0:
				bot.send_message(uid, history_textContinue, ParseMode.MARKDOWN)
			#bot.send_message(cid, "I sent you the history to our private chat")			
		else:
			bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")
	except Exception as e:
		bot.send_message(cid, str(e))
		log.error("Unknown error: " + str(e))  
		
def command_claim(bot, update, args):
	#game.pedrote = 3
	try:
		#Send message of executing command   
		cid = update.message.chat_id
		#Check if there is a current game 
		game = get_game(cid)
		if game:
			uid = update.message.from_user.id
			if uid in game.playerlist:				
				if (game.board.state.liberal_track + game.board.state.fascist_track) > 0:
					if len(args) > 0:
						#Data is being claimed
						claimtext = ' '.join(args)
						claimtexttohistory = "El jugador %s declara: %s" % (game.playerlist[uid].name, claimtext)
						bot.send_message(cid, "Tu declaración: %s fue agregada al historial." % (claimtext))
						game.history.append("%s" % (claimtexttohistory))
					else:					
						bot.send_message(cid, "Debes mandar un mensaje para hacer una declaración.")

				else:
					bot.send_message(cid, "No puedes hacer sin promulgar al menos una política.")
			else:
				bot.send_message(cid, "Debes ser un jugador del partido para declarar algo.")
				
		else:
			bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")
	except Exception as e:
		bot.send_message(cid, str(e))
		log.error("Unknown error: " + str(e))    

		
def command_claim_oculto(bot, update, args):
	try:
		#Send message of executing command   
		cid = update.message.chat_id
		uid = update.message.from_user.id
		
		# Busco en que juegos esta el jugador y agrego el historia oculto en los que este. (Futuro se
		for game_key, game in GamesController.games.items():
			#Solamente si el jugador esta en el partido y 
			if uid in game.playerlist:
				#Check if there is a current game
				if (game.board.state.liberal_track + game.board.state.fascist_track) > 0:
					if len(args) > 0:
						#Data is being claimed
						claimtext = ' '.join(args)
						claimtexttohistory = "El jugador %s declara: %s" % (game.playerlist[uid].name, claimtext)
						bot.send_message(uid, "Tu declaración: %s fue agregada al historial oculto." % (claimtext))
						game.hiddenhistory.append("%s" % (claimtexttohistory))
					else:					
						bot.send_message(uid, "Debes mandar un mensaje para hacer una declaración.")

				else:
					bot.send_message(uid, "No puedes hacer claim oculto sin promulgar al menos una política.")
			else:
				bot.send_message(uid, "No puedes hacer claim oculto si no estas en algun partido.")				
	except Exception as e:
		bot.send_message(uid, str(e))
		log.error("Unknown error: " + str(e))
		
def save_game(cid, groupName, game):
	#Check if game is in DB first
	cur = conn.cursor()			
	log.info("Searching Game in DB")
	query = "select * from games where id = %s;"
	cur.execute(query, [cid])
	dbdata = cur.fetchone()
	if cur.rowcount > 0:
		log.info('Updating Game')
		gamejson = jsonpickle.encode(game)
		#query = "UPDATE games SET groupName = %s, data = %s WHERE id = %s RETURNING data;"
		query = "UPDATE games SET groupName = %s, data = %s WHERE id = %s;"
		cur.execute(query, (groupName, gamejson, cid))
		#log.info(cur.fetchone()[0])
		conn.commit()		
	else:
		log.info('Saving Game in DB')
		gamejson = jsonpickle.encode(game)
		query = "INSERT INTO games(id , groupName  , data) VALUES (%s, %s, %s);"
		#query = "INSERT INTO games(id , groupName  , data) VALUES (%s, %s, %s) RETURNING data;"
		cur.execute(query, (cid, groupName, gamejson))
		#log.info(cur.fetchone()[0])
		conn.commit()

def load_game(cid):
	cur = conn.cursor()			
	log.info("Searching Game in DB")
	query = "SELECT * FROM games WHERE id = %s;"
	cur.execute(query, [cid])
	dbdata = cur.fetchone()

	if cur.rowcount > 0:
		log.info("Game Found")
		jsdata = dbdata[2]
		#log.info("jsdata = %s" % (jsdata))				
		game = jsonpickle.decode(jsdata)
		
		# For some reason the decoding fails when bringing the dict playerlist and it changes it id from int to string.
		# So I have to change it back the ID to int.				
		temp_player_list = {}		
		for uid in game.playerlist:
			temp_player_list[int(uid)] = game.playerlist[uid]
		game.playerlist = temp_player_list
		
		if game.board is not None and game.board.state is not None:
			temp_last_votes = {}	
			for uid in game.board.state.last_votes:
				temp_last_votes[int(uid)] = game.board.state.last_votes[uid]
			game.board.state.last_votes = temp_last_votes
		#bot.send_message(cid, game.print_roles())
		return game
	else:
		log.info("Game Not Found")
		return None

def delete_game(cid):
	cur = conn.cursor()
	log.info("Deleting Game in DB")
	query = "DELETE FROM games WHERE id = %s;"
	cur.execute(query, [cid])
	conn.commit()
	
	
#Testing commands
def command_ja(bot, update):
	uid = update.message.from_user.id
	if uid == ADMIN:
		cid = update.message.chat_id
		game = get_game(cid)
		answer = "Ja"
		for uid in game.playerlist:
			game.board.state.last_votes[uid] = answer
		MainController.count_votes(bot, game)
	

def command_nein(bot, update):	
	uid = update.message.from_user.id
	if uid == ADMIN:
		cid = update.message.chat_id
		game = get_game(cid)
		answer = "Nein"
		for uid in game.playerlist:
			game.board.state.last_votes[uid] = answer
		MainController.count_votes(bot, game)
		
def command_reloadgame(bot, update):  
	cid = update.message.chat_id
	
	try:
		game = GamesController.games.get(cid, None)
		groupType = update.message.chat.type
		if groupType not in ['group', 'supergroup']:
			bot.send_message(cid, "Tienes que agregarme a un grupo primero y escribir /reloadgame allá!")		
		else:			
			#Search game in DB
			game = load_game(cid)			
			if game:
				GamesController.games[cid] = game
				bot.send_message(cid, "Hay un juego comenzado en este chat. Si quieres terminarlo escribe /cancelgame!")				
				
				if not game.board:
					return
				
				# Ask the president to choose a chancellor								
				if game.board.state.nominated_chancellor:
					if len(game.board.state.last_votes) == len(game.player_sequence):
						print_board(bot, game, cid)
						MainController.count_votes(bot, game)
					else:
						print_board(bot, game, cid)
						MainController.vote(bot, game)
						bot.send_message(cid, "Hay una votación en progreso utiliza /calltovote para decirles a los otros jugadores. ")
				else:
					MainController.start_round(bot, game)
			else:				
				bot.send_message(cid, "No hay juego que recargar! Crea un nuevo juego con /newgame!")
			
			
	except Exception as e:
		bot.send_message(cid, str(e))
	
def command_anarquia(bot, update):	
	try:
		#Send message of executing command   
		cid = update.message.chat_id
		#Check if there is a current game 
		game = get_game(cid)
		
		if game:
			uid = update.message.from_user.id
			if uid in game.playerlist:
				# Se pregunta a los jugadores si irian a anarquia,
				# esto se hace para no tener que estar pasando 3 formular y esperar que todos voten
				# SI, mitad + 1 de jugadores decide ir por anarquia.
				# Se hace y se indica quienes quisieron ir a anarquia				
				MainController.decide_anarquia(bot, game)
			else:
				bot.send_message(cid, "Debes ser un jugador del partido para preguntar por anarquia.")

		else:
			bot.send_message(cid, "No hay juego en este chat. Crea un nuevo juego con /newgame")
	except Exception as e:
		bot.send_message(cid, str(e))
		log.error("Unknown error: " + str(e))    
		
def command_prueba(bot, update):	
	uid = update.message.from_user.id
	if uid == ADMIN:
		cid = update.message.chat_id
		game = get_game(cid)
		
		for uid in game.playerlist:
			game.playerlist[uid].name = game.playerlist[uid].name.replace("_", " ")
		
		#MainController.showHiddenhistory(bot, game)
		'''game = GamesController.games.get(cid, None)
		history_text = "Historial Oculto:\n\n" 
		for x in game.hiddenhistory:				
			history_text += x + "\n"
		bot.send_message(ADMIN, history_text, ParseMode.MARKDOWN)
		'''
		
def command_toggle_debugging(bot, update):
	uid = update.message.from_user.id
	if uid == ADMIN:
		cid = update.message.chat_id
		game = get_game(cid)
		# Informo que el modo de debugging ha cambiado
		game.is_debugging = True if not game.is_debugging else False
		bot.send_message(cid, "Debug Mode: ON" if game.is_debugging else "Debug Mode: OFF")

def command_jugadores(bot, update):	
	uid = update.message.from_user.id
	cid = update.message.chat_id
	
	game = get_game(cid)
	jugadoresActuales = "Los jugadores que se han unido al momento son:\n"
	for uid in game.playerlist:
		jugadoresActuales += "[%s](tg://user?id=%d)\n" % (game.playerlist[uid].name, uid)
					
	bot.send_message(game.cid, jugadoresActuales, ParseMode.MARKDOWN)	
		
def command_newgame_sql_command(bot, update, args):
	cid, uid = update.message.chat_id, update.message.from_user.id
	if uid == ADMIN:
		try:
			#Check if game is in DB first
			cursor = conn.cursor()			
			log.info("Executing in DB")
			#query = "select * from games;"
			query = " ".join(args)
			cursor.execute(query)
			#dbdata = cur.fetchone()
			
			if 'update' in args or 'insert' in args:
				conn.commit()
				bot.send_message(cid, 'Consulta commiteada')
			else:
					
				if cursor.rowcount > 0:
					bot.send_message(cid, 'Resultado de la consulta:')
					for table in cursor.fetchall():
						#bot.send_message(cid, len(str(table)))
						tabla_str = str(table)
						# Si supera el maximo de caracteres lo parto
						if len(tabla_str) < 4096:
							bot.send_message(cid, table)
						else:
							bot.send_message(cid, tabla_str[:-4090])
							bot.send_message(cid, tabla_str[4090:])
				else:
					bot.send_message(cid, 'No se obtuvo nada de la consulta')
		except Exception as e:
			bot.send_message(cid, 'No se ejecuto el comando debido a: '+str(e))
			conn.rollback()

def command_choose_posible_role(bot, update):
	cid, uid = update.message.chat_id, update.message.from_user.id
	choose_posible_role(bot, cid, uid)
	
def choose_posible_role(bot, cid, uid):
	frase_regex = "chooserole"
	pregunta_arriba_botones = "¿Qué rol quisieras ser?"
	chat_donde_se_pregunta = uid
	multipurpose_choose_buttons(bot, cid, uid, chat_donde_se_pregunta, frase_regex, pregunta_arriba_botones, opciones_choose_posible_role)

def callback_choose_posible_role(bot, update):
	callback = update.callback_query
	log.info('callback_choose_posible_role called: %s' % callback.data)	
	regex = re.search("(-[0-9]*)\*chooserole\*(.*)\*([0-9]*)", callback.data)
	cid, strcid, opcion, uid, struid = int(regex.group(1)), regex.group(1), regex.group(2), int(regex.group(3)), regex.group(3)
	
	# Busco el juego actual y le pongo al jugador su preferencia, solamente si el juego no empezo hago el seteo de preferencia
	#bot.edit_message_text("Mensaje Editado: Has elegido el Rol: %s" % opcion, cid, callback.message.message_id)
	mensaje_edit = ''
	
	game = get_game(cid)
	
	if game:
		if game.board:
			mensaje_edit = 'El juego ya comenzó, intentalo cuando el juego no haya empezado'
		else:
			if uid in game.playerlist:
				mensaje_edit = 'Mensaje Editado: Has elegido el Rol: %s' % opcion
				game.playerlist[uid].preference_rol = opcion
				choose_posible_role(bot, cid, uid)
			else:
				mensaje_edit = 'No estas unido a esta partida, intentalo cuando te hayas unido'			
	else:
		mensaje_edit = 'No hay juego creado, intentalo cuando el juego este creado'		
	
	try:
		bot.edit_message_text(mensaje_edit, cid, callback.message.message_id)
	except Exception as e:
		bot.edit_message_text(mensaje_edit, uid, callback.message.message_id)
	
	#bot.send_message(cid, "Ventana Juego: Has elegido el Rol %s" % opcion)
	#bot.send_message(uid, "Ventana Usuario: Has elegido el Rol %s" % opcion)	

def multipurpose_choose_buttons(bot, cid, uid, chat_donde_se_pregunta, comando_callback, mensaje_pregunta, opciones_botones):	
	btns = []
	# Creo los botones para elegir al usuario
	for opcion in opciones_botones:
		txtBoton = ""
		comando_op = opciones_botones[opcion]								
		for comando in comando_op["comandos"]:
			txtBoton += comando_op["comandos"][comando] + " "			
		txtBoton = txtBoton[:-1]
		datos = str(cid) + "*" + comando_callback + "*" + str(opcion) + "*" + str(uid)
		btns.append([InlineKeyboardButton(txtBoton, callback_data=datos)])
	btnMarkup = InlineKeyboardMarkup(btns)
	#for uid in game.playerlist:
	bot.send_message(chat_donde_se_pregunta, mensaje_pregunta, reply_markup=btnMarkup)

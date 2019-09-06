import json
from datetime import datetime
from random import shuffle

from Boardgamebox.Player import Player
from Boardgamebox.Board import Board
from Boardgamebox.State import State

class Game(object):
	def __init__(self, cid, initiator, groupName):
		self.playerlist = {}
		self.player_sequence = []
		self.cid = cid
		self.board = None
		self.initiator = initiator
		self.dateinitvote = None
		self.history = []
		self.hiddenhistory = []
		self.is_debugging = False
		self.groupName = groupName
		self.tipo = 'SecretHitler'   
    
	def add_player(self, uid, player):
		self.playerlist[uid] = player

	def get_hitler(self):
		for uid in self.playerlist:
			if self.playerlist[uid].role == "Hitler":
				return self.playerlist[uid]

	def get_fascists(self):
		fascists = []
		for uid in self.playerlist:
			if self.playerlist[uid].role == "Fascista":
				fascists.append(self.playerlist[uid])
		return fascists

	def shuffle_player_sequence(self):
		for uid in self.playerlist:
			self.player_sequence.append(self.playerlist[uid])
		shuffle(self.player_sequence)

	def remove_from_player_sequence(self, Player):
		for p in self.player_sequence:
			if p.uid == Player.uid:
				p.remove(Player)

	def print_roles(self):
		try:
			rtext = ""
			if self.board is None:
				#game was not started yet
				return rtext
			else:
				for p in self.playerlist:
					name = self.playerlist[p].name
					role = self.playerlist[p].role
					preference_rol = self.playerlist[p].preference_rol
					muerto = self.playerlist[p].is_dead					
					rtext += "El rol de %s %sera %s %s" % (name, "(muerto) " if muerto else "", role, ("" if preference_rol == "" else "queria ser " + preference_rol))										
					rtext +=  "\n"
				return rtext
		except Exception as e:
			rtext += str(e)
class Player(object):
    def __init__(self, name, uid):
        self.name = name
        self.uid = uid
        self.role = None
        self.party = None
        self.is_dead = False
        self.inspected_players = {}
        self.was_investigated = False
        #"Liberal","Fascista","Hitler"
        self.preference_rol = ""

    def get_private_info(self, game):
        board = "--- *Info del Jugador {}* ---\n".format(self.name)
        board += "Eres *{}* y tu afiliacion es *{}*\n".format(self.role, self.party)
        player_number = len(game.playerlist)
        if self.role == "Fascista":
            fascists = game.get_fascists()
            if player_number > 6:
                fstring = ""
                for f in fascists:
                    if f.uid != self.uid:
                        fstring += f.name + ", "
                fstring = fstring[:-2]
                if not game.is_debugging:
                    board += "Tus compañeros fascistas son: *{}*\n".format(fstring)
            hitler = game.get_hitler()
            board += "Hitler es: *{}*".format(hitler.name)
        elif self.role == "Hitler":
            if player_number <= 6:
                fascists = game.get_fascists()
                board +=  "Tu compañero fascista es: *{}*".format(fascists[0].name)
        return board

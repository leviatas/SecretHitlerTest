
class PlayerStats(object):
    def __init__(self, uid):
        self.uid = uid
        self.data = {}
        # achivements 
        # data[tipo_juego]
        # // Achivements logrados id:nombre
        # data[tipo_juego]['achivements'] = {} 
        # // datos estadisticos nombre:cantidad
        # data[tipo_juego]['data'] = {}
    
    def getStats(self, tipo_juego):
        if tipo_juego in self.data:
            return self.data[tipo_juego]
        else:
            None

    def getSecretHitlerStats(self):
        return self.getStats("SecretHitler")

    def change_data_stat(self, tipo_juego, stat_name, amount):
        # Si el usuario no tiene datos del juego lo inicializo.
        if tipo_juego not in self.data:
            self.data[tipo_juego] = {}
            self.data[tipo_juego]['data'] = {}
        # Si el stats incremental no esta en la data, lo agrego directamente, sino le aplico la cantidad
        if stat_name not in self.data[tipo_juego]['data']:
            self.data[tipo_juego]['data'][stat_name] = amount
        else:
            self.data[tipo_juego]['data'][stat_name] += amount




                
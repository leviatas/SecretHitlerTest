class Player(object):
    def __init__(self, name, uid):
        self.name = name
        self.uid = uid
        self.role = None
        self.party = None
        self.is_dead = False
        self.inspected_players = {}
    def __init__(self, data):
        for name, value in data.items():
            setattr(self, name, self._wrap(value))

    def _wrap(self, value):
        if isinstance(value, (tuple, list, set, frozenset)): 
            return type(value)([self._wrap(v) for v in value])
        else:        
            return Player(value) if isinstance(value, dict) else value

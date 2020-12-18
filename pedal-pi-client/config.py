import uuid
import random
import string

DEBUG = True
# randomly generate a secret key 
SECRET_KEY = bytes("".join(random.choice(string.printable) for _ in range(20)), encoding="ascii")

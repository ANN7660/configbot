# Dummy audioop module for Python 3.13
def add(a, b, width): return b
def mul(a, factor, width): return a
def max(a, width): return 0
def avg(a, width): return 0
def rms(a, width): return 0

def ratecv(fragment, width, channels, inrate, outrate, state, weightA=1, weightB=0):
    return fragment, state

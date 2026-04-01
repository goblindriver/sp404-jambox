# Vendored from spEdit404
def add_padding(padee, length):
    padee = str(padee)
    while len(padee) < length:
        padee = '0' + padee
    return padee

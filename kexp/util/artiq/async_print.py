from artiq.experiment import rpc

@rpc(flags={'async'})
def aprint(*args):
    print(*args)
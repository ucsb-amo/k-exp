class ExptParams():
    def __init__(self):
        pass

    def params_to_dataset(self,expt):
        try:
            param_keys = list(vars(self))
            for key in param_keys:
                value = vars(self)[key]
                expt.set_dataset(key, value)
        except Exception as e: 
            print(e)
            
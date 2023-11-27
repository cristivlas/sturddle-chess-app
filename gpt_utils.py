import json


def get_token_count(model, messages, functions):
    '''
    This function provides a quick-and-dirty approximation of the token count.

    There is a more accurate implementation at:
    https://stackoverflow.com/questions/77168202/calculating-total-tokens-for-api-request-to-chatgpt-including-functions
    which depends on the tiktoken module; the titktoken module does not seem to have a correct recipe for Buildozer, as
    it fails on Android with a bad ELF error.
    '''
    msg = json.dumps(messages)
    fun = json.dumps(functions) if functions else ''
    tok = (len(msg) + len(fun)) / 3.4  # approximate characters per token.
    return int(tok)


_limits = {
    'gpt-3.5-turbo-1106': 16385,
    'gpt-4': 8192,
    'gpt-4-1106-preview': 128000,
}


def get_token_limit(model):
    return _limits.get(model, 4096)

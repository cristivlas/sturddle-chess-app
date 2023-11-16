'''

import tiktoken

# https://stackoverflow.com/questions/77168202/calculating-total-tokens-for-api-request-to-chatgpt-including-functions
def get_token_count(model, messages, functions):
    # Initialize message settings to 0
    msg_init = 0
    msg_name = 0
    msg_end = 0
    
    # Initialize function settings to 0
    func_init = 0
    prop_init = 0
    prop_key = 0
    enum_init = 0
    enum_item = 0
    func_end = 0
    
    # if model in [
    #     "gpt-3.5-turbo-0613",
    #     "gpt-3.5-turbo-1106",
    #     "gpt-4-0613",
    # ]:
    if True:
        # Set message settings for above models
        msg_init = 3
        msg_name = 1
        msg_end = 3
        
        # Set function settings for the above models
        func_init = 7
        prop_init = 3
        prop_key = 3
        enum_init = -3
        enum_item = 3
        func_end = 12
    
    enc = tiktoken.encoding_for_model(model)
    
    msg_token_count = 0
    for message in messages:
        msg_token_count += msg_init  # Add tokens for each message
        for key, value in message.items():
            msg_token_count += len(enc.encode(value))  # Add tokens in set message
            if key == "name":
                msg_token_count += msg_name  # Add tokens if name is set
    msg_token_count += msg_end  # Add tokens to account for ending
    
    func_token_count = 0
    if len(functions) > 0:
        for function in functions:
            func_token_count += func_init  # Add tokens for start of each function
            f_name = function["name"]
            f_desc = function["description"]
            if f_desc.endswith("."):
                f_desc = f_desc[:-1]
            line = f_name + ":" + f_desc
            func_token_count += len(enc.encode(line))  # Add tokens for set name and description
            if len(function["parameters"]["properties"]) > 0:
                func_token_count += prop_init  # Add tokens for start of each property
                for key in list(function["parameters"]["properties"].keys()):
                    func_token_count += prop_key  # Add tokens for each set property
                    p_name = key
                    p_type = function["parameters"]["properties"][key]["type"]
                    p_desc = function["parameters"]["properties"][key]["description"]
                    if "enum" in function["parameters"]["properties"][key].keys():
                        func_token_count += enum_init  # Add tokens if property has enum list
                        for item in function["parameters"]["properties"][key]["enum"]:
                            func_token_count += enum_item
                            func_token_count += len(enc.encode(item))
                    if p_desc.endswith("."):
                        p_desc = p_desc[:-1]
                    line = f"{p_name}:{p_type}:{p_desc}"
                    func_token_count += len(enc.encode(line))
        func_token_count += func_end
    
    return msg_token_count + func_token_count
'''


def get_token_count(model, messages, functions):
    '''
    Quick-and-dirty workaround for tiktoken.so being broken on Android (bad ELF).
    '''
    msg = json.dumps(messages)
    fun = json.dumps(functions)
    tok = (len(msg) + len(fun)) / 4.5  # approximate characters per token.
    return int(tok)


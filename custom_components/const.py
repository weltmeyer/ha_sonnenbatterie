import logging

LOGGER = logging.getLogger(__package__)

DOMAIN = "sonnenbatterie"

def flattenObj(prefix,seperator,obj):
    result={}
    for field in obj:
        val=obj[field]
        valprefix=prefix+seperator+field
        if type(val) is dict:
            sub=flattenObj(valprefix,seperator,val)
            result.update(sub)
        else:
            result[valprefix]=val
    return result

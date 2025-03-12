colours = {
    "red": "91",
    "green": "92",
    "yellow": "93",
    "blue": "94",
    "magenta": "96",
    "cyan": "97"
}


def colour_text(text, colour=""):
    prefix = ""
    suffix = ""
    colour = colour.lower()
    if colour in colours:
        prefix = "\033[" + colours[colour] + "m"
        suffix = "\033[0m"
    return prefix + str(text) + suffix


def seconds_to_text(seconds, joiner=""):
    seconds = round(seconds)
    text = {"h": seconds // 3600, "m": seconds // 60 % 60, "s": seconds % 60}
    if joiner == "":
        text = [str(v) + k for k, v in text.items() if v > 0]
    else:
        if text["h"] == 0:
            del text["h"]
        text = [str(v).rjust(2, "0") for k, v in text.items()]
    return joiner.join(text)

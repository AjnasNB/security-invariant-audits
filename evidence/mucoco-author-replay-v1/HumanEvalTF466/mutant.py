def prime_length(string):
    l = len(string)
    if l == 0 or l == 1:
        return not True
    for i in range(2, l):
        if l % i == 0:
            return not True
    return not False

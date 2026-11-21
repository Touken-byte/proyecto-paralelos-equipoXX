"""Sprites chibi: bombero 33x51 y veterinaria 39x51. 1 caracter = 1 pixel, "." = transparente."""

PAL = {
    "0": "1e5acd", "1": "ccd2ff", "2": "1e6eeb", "3": "e02228", "4": "966846", "5": "6e482e",
    "A": "0e0a14", "B": "ff9678", "C": "ec483a", "D": "ffec82", "E": "ffce32", "F": "d02222",
    "G": "e89618", "H": "96161a", "I": "f0604c", "J": "d02824", "K": "ffce34", "L": "1c1c24",
    "M": "a01a1c", "N": "785244", "O": "966c5c", "P": "5c3c30", "Q": "462c24", "R": "ffe4c6",
    "S": "fcd2b0", "T": "603e32", "U": "f4c09e", "V": "e2a080", "W": "823e22", "X": "f28692",
    "Y": "b01e2c", "Z": "d23c46", "a": "ec6064", "b": "e4aa88", "c": "b01a1e", "d": "8c141a",
    "e": "6e1016", "f": "624028", "g": "3c281e", "h": "545260", "i": "2e2c38", "j": "22202a",
    "k": "82c3ff", "l": "3e98ff", "m": "1e70ec", "n": "ebeefc", "o": "d6dcf8", "p": "144cc4",
    "q": "6eb9ff", "r": "3c96fc", "s": "2272e8", "t": "2860e6", "u": "ec4c4c", "v": "f0f2ff",
    "w": "46a0ff", "x": "2276f0", "y": "1654c8", "z": "bac4ec",
}

# letras que cambian con la skin (el resto del sprite no cambia)
GRUPOS = {
    "bombero": {"R": "BCFHIJMYZacde", "U": "DEGK"},
    "vet": {"G": "02klmpqrstwxy", "W": "1novz"},
}

BOMBERO = [
    "..........AAAAAAAAAAAAA..........",
    "........AABBBBCCCCCCCCCAA........",
    "......AABBBBBCDDDEECCCCCCAA......",
    ".....ABBBBBBCDDDEEEECCCCFFFA.....",
    "....ABBBBBBCCDDDEEEECCCFFFFFA....",
    "....ABBBBBCCDDDEEEEEGCFFFFFFA....",
    "...ABBBBCCCCDDDEEEEGGFFFFFFFFA...",
    "..ABBBBCCCCCDDEEEEGGGFFFFFFFFFA..",
    "..ABBBCCCCCCDEEEEEGGGFFFFFFFFFA..",
    ".ABBBCCCCCCCDEEEEGGGGFFFFFFFFFHA.",
    ".ABBCCCCCCCCCCEEEGGFFFFFFFFFFHHA.",
    "ABBCCCCCCCCCCCCFGFFFFFFFFFFFHHHHA",
    "ABCCCCCCCCCAAAAAAAAAAAFFFFFHHHHHA",
    "ACCCCCCCCCAIIIIIIIJJJJAFFFHHHHHHA",
    "ACCCCCCCAAIIIIIJJJJJJJJAAHHHHHHHA",
    "ACCCCCCAKKKKLLLLLLLLKKKKMAHHHHHHA",
    "ACCCCCAIKKKKLLLLLLLLKKKKMMAHHHHHA",
    "ACCCCCAIIJJJJJJJJJJJMMMMMMAHHHHHA",
    "ACCCCAJJJJJJJJJJJJMMMMMMMMMAHHHHA",
    ".AAACAAAAJJJJJJMMMMMMMMMAAAAHAAA.",
    "...AANONNAAAAAAAAAAAAAAAPQNNA....",
    "..AONNNNPNPRRPSSSSSSPPPPQQNNPA...",
    ".AOONNPNPPRRRSSSSSSSSSSPQQNNPPA..",
    ".AONNAPNPTTTTSSSSSSTTTTPQQANPPA..",
    ".AOAASANPRRRSSSSSSSSSUUPQARAAQA..",
    ".AARRSUNPAAAASSSSSSAAAAPQRRSUAA..",
    ".AARSSURA..AASSSSSSA..AAURSSUAA..",
    ".AARVSURAAAAASSSSSSAAAAAURSVUAA..",
    "..ARSUURAAWWASSSSSUAAWWAURSUUA...",
    "..AASUURAAWWASSSSUUAAWWAUSSUAA...",
    "...ASAAQXXSSSYSSSUYUUUXXNAAUA....",
    "....AQAAXXSSSSZaaZUUUUXXAAPA.....",
    ".....A...SSSSSSUUUUUUUU...A......",
    "..........AAAAbbbbAAAA...........",
    ".........AAFALbbbbLABAA..........",
    "........ACFFALcddcLABBCA.........",
    ".......AKKKHALcddcLABKKKA........",
    "......ABKKKHALcddcLABKKKHA.......",
    "......AAAAAHALcddcLACAAAAA.......",
    "......AHHHeAALcddcLAAHHHeA.......",
    "......AAAeeALLcddcLLAHeAAA.......",
    ".....ARRSAACLLcddcLLHAARSSA......",
    ".....ARSSUACLLcddcLLHARSSUA......",
    ".....ARSUACCLLcddcLLHHASUUA......",
    ".....ASSUAfgfgKDDKgfgfASUUA......",
    "......AAAAfgfgKDDKgfgfAAAA.......",
    "..........AAAAAAAAAAAA...........",
    "..........AAAAAAAAAAAA...........",
    ".........AhhhiiAAhhhiiA..........",
    ".........AiijjjAAiijjjA..........",
    "..........AAAAA..AAAAA...........",
]

VET = [
    "...........AAAAAAAAAAAAA...............",
    ".........AAkkkklllllllllAA.............",
    ".......AAkkkkkllllllllllllAA...........",
    "......AkkkkkkllllllllllllmmmA..........",
    ".....Akkkkkkllll...lllllmmmmmA.........",
    ".....Akkkkklllll...llllmmmmmmA.........",
    "....Akkkklllll.......lmmmmmmmmA........",
    "...Akkkkllllll.....nommmmmmmmmmA.......",
    "...Akkklllllllll...lmmmmmmmmmmmA.......",
    "..Akkkllllllllll..ommmmmmmmmmmmpA......",
    "..AkkllllllllllllmmmmmmmmmmmmmppA......",
    ".AkkllllllllllllmmmmmmmmmmmmmppppA.....",
    ".AklllllllllAAAAAAAAAAAmmmmmpppppA.....",
    ".AlllllllllAqqqqqqqrrrrAmmmppppppAA....",
    ".AlllllllAAqqqqqrrrrrrrrAApppppppANA...",
    ".AllllllAqqqqqrrrrrrrrrrrsAppppppANA...",
    ".AlllllAqqqqrrrrrrrrrrrssssApppppANPA..",
    ".AlllllAqqrrrrrrrrrrrssssssApppppANPA..",
    ".AllllArrrrrrrrrrrrsssssssssAppppAOPPA.",
    "..AAAlAAAArrrrrrsssssssssAAAApAAAOPPPA.",
    ".AOONAOONNAAAAAAAAAAAAAAAPPPPANNONPQPA.",
    "AOOONQOONONNPPPPSNNNONNPPOPPPQNONQPPOPA",
    "AOOQNOONONNPPPSSSNNNNNPPPPPOQQOQNNPOPQA",
    "AQONONNNNNTTTTSSSSSNSTTTUUPQQQNNNPOPQQA",
    ".AOOAASNNNRRRSSSSSSSSSUUUUQQOQNNNOQPPQA",
    ".AOARRSNNAAAAASSSSSSAAAAAURQQQANOPPPPOA",
    ".AQARSSNPA..AASSSSSSA..AAURQQQAONPPPOQA",
    ".ANARVSURAAAAASSSSSSAAAAAURSVUANPPPOQQA",
    "..AARSUURAAttASSSSSUAAttAURSUUANPQOPQQA",
    "..AOASUURAAttASSSSUUAAttAUSSUANQPOPPQQA",
    "....AAAAAXXSSSSYYYYUUUUXX.AAUANNOPPPQA.",
    "........AXXSSSSSuuUUUUUXX...AANOPPQQOA.",
    ".........ASSSSSSUUUUUUUU.....AOPQPPOQA.",
    "..........AAAAAbbbbAAAA.....AOQPPPOQQA.",
    "..........AAoAAbbbbAA.AA....ANNPPOPQQQA",
    "..........vooAAwwxyAA..vA...ANNPOQQQQOA",
    ".........vvozAAwwxyAA.vvoA...APOAPQQOA.",
    ".........voozAAwxxyAA.voozA...APAPQOQA.",
    "..........AAzAAwxxyAAvAAAAA....A.AAQA..",
    ".......AkklmAAAwxxy0AAkklmA........A...",
    ".......AAAppAvAwxxyA0AlmAAAA...........",
    "......ARRSAAvvAwxyy000AARRRSA..........",
    "......ARSSUAvvAwxyyAzzzARRSSUA.........",
    "......ARSUAv111xxyy111zARSSUA2.........",
    "......ASSUAv1.1xxyy1.1zASSUUA2AA.......",
    ".......AAAAv111xxyy111zAAAAAvvooA......",
    "...........AAAAAAAAAAAA.A..v3oooA......",
    "...........AAAAAAAAAAAA.A.v333ozA......",
    "..........A44445AA44445AAvvo3ozzA......",
    "..........A45555AA45555AAvooozzzA......",
    "...........AAAAA..AAAAA..AAAAAAA.......",
]


def construir(pers, skin):
    """Surface del personaje (escala 1). skin = {} (clasico) o {letra_de_grupo: color}."""
    import pygame
    filas = BOMBERO if pers == "bombero" else VET
    grupos = GRUPOS["bombero" if pers == "bombero" else "vet"]
    base = {k: tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)) for k, v in PAL.items()}

    def lum(c):
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

    ref = {}
    for g, letras in grupos.items():
        tot = sum(f.count(l) for f in filas for l in letras) or 1
        ref[g] = sum(lum(base[l]) * f.count(l) for f in filas for l in letras) / tot
    h, w = len(filas), len(filas[0])
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, fila in enumerate(filas):
        for x, ch in enumerate(fila):
            if ch == ".":
                continue
            col = base[ch]
            for g, letras in grupos.items():
                if ch in letras and g in skin:
                    k = lum(col) / ref[g]
                    col = tuple(max(0, min(255, int(c * k))) for c in skin[g])
            s.set_at((x, y), col + (255,))
    return s

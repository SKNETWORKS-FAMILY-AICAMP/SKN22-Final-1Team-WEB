from enum import Enum

class CurrentLength(str, Enum):
    SHORT = "쇼트"
    BOB = "보브"
    SEMILONG = "세미롱"
    LONG = "롱"

class TargetVibe(str, Enum):
    CUTE = "귀여움"
    CHIC = "시크함"
    NATURAL = "자연스러움"
    ELEGANT = "우아함"

class ScalpType(str, Enum):
    STRAIGHT = "직모"
    WAVED = "웨이브"
    CURLY = "곱슬"
    DAMAGED = "손상모"

class HairColour(str, Enum):
    BLACK = "블랙"
    BROWN = "브라운"
    ASHEN = "애쉬"
    BLEACHED = "블리치"

class BudgetRange(str, Enum):
    BELOW3 = "3만 이하"
    FROM3TO5 = "3만 ~ 5만"
    FROM5TO10 = "5만~ 10만"
    OVER10 = "10만 이상"
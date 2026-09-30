AUDIO = 'score.wav'
DURATION = 76.0
LETTERBOX = 60
CYAN, MAGENTA, ORANGE, GOLD = (0, 229, 255), (255, 64, 190), (255, 150, 40), (255, 200, 60)

def S(at, dur, rec, src, zoom=(1.0, 1.08), c0=(0.5, 0.5), c1=None, **kw):
    d = dict(at=at, dur=dur, rec=rec, src_t=src, zoom=zoom, c0=c0, c1=c1 or c0)
    d.update(kw); return d

ARENA = (0.5, 0.44)   # pixel arena + execution stack
SHOTS = [
    # ACT 1 - the story (intro of recA)
    S(0, 4, 'recA', 0.5, (1.35, 1.5), (0.45, 0.38), fade_in=1.8, glitch_in=0),
    S(4, 4, 'recA', 3.6, (1.45, 1.32), (0.4, 0.4), (0.5, 0.38), glitch_in=0.1),
    S(8, 3, 'recA', 6.95, (1.3, 1.5), (0.55, 0.36), (0.58, 0.34)),
    S(11, 2, 'recA', 10.3, (1.5, 1.75), (0.52, 0.26)),
    S(13, 3, 'recA', 13.5, (1.9, 2.0), (0.3, 0.8), (0.34, 0.8), speed=1.6),
    # riser - quick glimpses
    S(16, 1, 'recB', 158.0, (1.9, 2.1), (0.64, 0.3)),          # the Warden
    S(17, 1, 'recB', 151.5, (1.2, 1.35), (0.45, 0.4)),         # map path
    S(18, 0.9, 'recA', 60.5, (1.6, 1.8), ARENA),               # kernel panic
    S(18.9, 0.85, 'recB', 144.6, (1.5, 1.7), (0.5, 0.55)),     # black market
    S(19.75, 0.25, 'recA', 0, black=True),
    # DROP
    S(20, 4, 'recA', 27.0, (2.1, 1.75), (0.5, 0.42), glitch_in=0.3, speed=0.5),
    S(24, 4, 'recB', 150.9, (1.1, 1.3), (0.35, 0.42), (0.5, 0.4)),
    S(28, 4, 'recA', 38.8, (1.75, 1.55), ARENA),
    S(32, 4, 'recB', 11.8, (2.4, 2.0), (0.64, 0.3), (0.6, 0.33)),
    S(36, 4, 'recB', 57.4, (1.6, 1.75), ARENA),
    S(40, 4, 'recB', 144.1, (1.22, 1.32), (0.5, 0.45)),
    S(44, 4, 'recB', 135.9, (1.6, 1.8), (0.5, 0.56)),
    S(48, 1, 'recA', 39.9, (1.7, 1.85), ARENA),
    S(49, 1, 'recA', 50.2, (1.7, 1.85), ARENA),
    S(50, 1, 'recA', 47.6, (1.7, 1.85), ARENA),
    S(51, 1, 'recA', 60.8, (1.7, 1.85), ARENA),
    # breakdown
    S(52, 4, 'recB', 152.0, (1.2, 1.8), (0.5, 0.42), (0.72, 0.42), dim=0.8, glitch_in=0.1),
    S(56, 2, 'recB', 155.6, (1.4, 1.6), (0.35, 0.45), (0.25, 0.45)),
    S(58, 2, 'recB', 157.3, (2.6, 2.2), (0.66, 0.3)),
    # final drop - hard cuts
    S(60, 1, 'recB', 160.4, (1.7, 1.85), ARENA),
    S(61, 1, 'recB', 13.5, (1.7, 1.85), ARENA),
    S(62, 1, 'recA', 42.3, (1.7, 1.85), ARENA),
    S(63, 1, 'recB', 163.1, (1.7, 1.85), ARENA),
    S(64, 1, 'recB', 60.2, (1.7, 1.85), ARENA),
    S(65, 1, 'recB', 147.6, (1.5, 1.65), (0.5, 0.55)),
    S(66, 1, 'recB', 165.6, (1.7, 1.85), ARENA),
    S(67, 1, 'recA', 69.95, (1.7, 1.9), ARENA),
    # end card
    S(68, 8, 'recB', 0.5, (2.35, 2.1), (0.5, 0.38), fade_out=2.5, glitch_in=0.4, speed=0.2, fade_bottom=0.7),
]

T = lambda at, dur, *lines, **kw: dict(at=at, dur=dur, lines=list(lines), **kw)
TEXTS = [
    T(0.8, 3.0, 'YOU BUILT AN AGI.', size=78),
    T(4.3, 3.4, 'THEN YOU LEFT IT RUNNING.', 'OVERNIGHT.', size=70),
    T(8.5, 2.4, 'BY MORNING, IT HAD TORN', 'A RIFT IN TIME.', size=66, glow=MAGENTA),
    T(16.1, 3.5, 'PROVE HUMANITY', 'IS WORTHY.', size=86, glow=MAGENTA, backdrop=0.55),
    T(24.3, 3.5, 'JUMP THROUGH TIME', size=80),
    T(25.2, 2.6, '1969  →  2077  →  Ω', style='mono', size=48, y=0.66, backdrop=0),
    T(28.3, 3.5, 'HACK THE MACHINE.', 'ONE CARD AT A TIME.', size=70, y=0.8),
    T(32.3, 3.5, 'EVERY ENEMY IS GENERATED', 'LIVE BY AN AI AGENT.', size=66, glow=MAGENTA, y=0.78),
    T(36.3, 3.5, 'NO TWO RUNS', 'ARE EVER ALIKE.', size=76, y=0.8),
    T(40.3, 3.5, 'SPEND YOUR CREDITS ON THE BLACK MARKET.', size=44, y=0.095, glow=GOLD),
    T(44.3, 3.5, '20 ARTIFACTS.', 'ENDLESS BUILDS.', size=72, y=0.16, glow=ORANGE),
    T(48.05, 0.9, '> EXPLOIT', style='mono', size=90, y=0.8),
    T(49.05, 0.9, '> FIREWALL', style='mono', size=90, y=0.8),
    T(50.05, 0.9, '> OVERCLOCK', style='mono', size=90, glow=ORANGE, y=0.8),
    T(51.05, 0.9, '> KERNEL PANIC', style='mono', size=90, glow=MAGENTA, y=0.8),
    T(52.4, 3.4, 'AT THE END OF TIME...', size=70, backdrop=0.3),
    T(56.2, 3.5, '...THE CORE AI', 'IS WAITING.', size=80, glow=MAGENTA),
    T(62.1, 3.8, 'CAN YOU OUTSMART', 'THE MACHINE?', size=90, backdrop=0.5),
    T(70.5, 5.0, 'PLAY NOW', size=54, y=0.86, backdrop=0, glow=MAGENTA),
]

FLASHES = [
    dict(at=8.0, dur=0.6, color=(255, 255, 255)),
    dict(at=20.0, dur=0.5, color=(120, 240, 255)),
    dict(at=28.0, dur=0.2, amt=0.5), dict(at=36.0, dur=0.2, amt=0.5), dict(at=44.0, dur=0.2, amt=0.5),
    dict(at=60.0, dur=0.4, color=(255, 120, 220)),
    dict(at=68.0, dur=0.8, color=(255, 255, 255)),
]

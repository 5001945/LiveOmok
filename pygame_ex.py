import sys
from enum import Enum

import pygame
from pygame.locals import *

from animations import SpaceAnimation


class Color(Enum):
    BLUE = (0, 0, 255)
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)

class Team(Enum):
    NONE = 0
    BLACK = 1
    WHITE = 2

FPS = 30


class Space:
    def __init__(self) -> None:
        self.team: Team = Team.NONE
        self.turn: int | None = None
        self.animation = SpaceAnimation(self)

    # def move_animation(total_frame: int):
        # yield 


def main():
    pygame.init()
    pygame.display.set_caption("Pygame Example")  # 창 제목 설정
    displaysurf = pygame.display.set_mode((640, 480))
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
        displaysurf.fill(Color.WHITE)
        pygame.draw.arc()

        pygame.display.update()
        clock.tick(FPS)


if __name__ == '__main__':
    main()

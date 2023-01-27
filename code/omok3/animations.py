from math import pi, floor
from typing import TYPE_CHECKING

import pygame
from pygame.locals import *
# from pygame import gfxdraw

if TYPE_CHECKING:
    from code.omok3.omok3 import Space  # Prevent circular import


class Animation:
    def __init__(self, parent: 'Space', total_frame: int, infinite_loop: bool = False) -> None:
        self.parent = parent
        self.total_frame = total_frame
        self.infinite_loop = infinite_loop
        self.current_frame = 0

    def play(self):
        # raise NotImplementedError()
        if self.current_frame >= self.total_frame:
            if self.infinite_loop:
                self.current_frame = 0
            else:
                return "Animation ends"

        self.current_frame += 1
        yield self._draw_frame()

    def _draw_frame(self):
        return None

    @property
    def frame(self):
        return self.current_frame - 1


class SpaceAnimation(Animation):
    def __init__(self, parent: 'Space') -> None:
        super().__init__(parent, total_frame=1, infinite_loop=True)


class StoneIdleAnimation(Animation):
    def __init__(self, parent: 'Space') -> None:
        super().__init__(parent, total_frame=1, infinite_loop=True)

    def _draw_frame(self):
        return pygame.draw.circle(
            self.parent.board.game.displaysurf,
            self.parent.team.color(),
            self.parent.rect.center,
            17
        )
        # return gfxdraw.filled_circle(
        #     self.parent.board.game.displaysurf,
        #     self.parent.rect.centerx,
        #     self.parent.rect.centery,
        #     20,
        #     self.parent.team.color(),
        # )


class StoneReservedAnimation(Animation):
    # 바둑알을 놓을 때 테두리를 따라 한 바퀴 휠을 채운다.
    def __init__(self, parent: 'Space') -> None:
        super().__init__(parent, total_frame=60, infinite_loop=False)

    def _draw_frame(self):
        return pygame.draw.arc(
            self.parent.board.game.displaysurf,
            self.parent.team.color(),
            self.parent.rect.inflate(-16, -16),
            start_angle=pi/2 - 2*pi*(self.current_frame/self.total_frame),
            stop_angle=pi/2,
            width=3
        )
        # return gfxdraw.arc(
        #     self.parent.board.game.displaysurf,
        #     self.parent.rect.centerx,
        #     self.parent.rect.centery,
        #     17,
        #     -91,
        #     floor(-90 + 362 * (self.frame/self.total_frame)),
        #     self.parent.team.color(),
        # )


class StoneDeployedAnimation(Animation):
    def __init__(self, parent: 'Space') -> None:
        super().__init__(parent, total_frame=10, infinite_loop=False)

    def _draw_frame(self):
        # 방사형으로 8개 생성
        for i in range(8):
            center = pygame.Vector2(self.parent.rect.center)
            start_point = pygame.Vector2(20 + max(self.frame-3, 0) * 7/6, 0)
            end_point = pygame.Vector2(20 + min(self.frame, 2) * 7/2, 0)
            start_point_rotated = start_point.rotate(22.5 + 45*i)
            end_point_rotated = end_point.rotate(22.5 + 45*i)

            pygame.draw.aaline(
                self.parent.board.game.displaysurf,
                self.parent.team.color(),
                center + start_point_rotated,
                center + end_point_rotated
            )
        return pygame.draw.circle(
            self.parent.board.game.displaysurf,
            self.parent.team.color(),
            self.parent.rect.center,
            17
        )

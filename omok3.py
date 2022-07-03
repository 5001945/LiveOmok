import sys
from enum import Enum

import pygame
from pygame.locals import *

from animations import SpaceAnimation, StoneDeployedAnimation, StoneIdleAnimation, StoneReservedAnimation


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

    def color(self) -> tuple[int, int, int]:
        if self == Team.NONE:
            return (127, 127, 127)
        elif self == Team.BLACK:
            return (0, 0, 0)
        elif self == Team.WHITE:
            return (255, 255, 255)
        else:
            raise ValueError()


class State(Enum):
    EMPTY = 0
    BLACK = 1
    WHITE = 2
    BLACK_RESERVED = 3
    WHITE_RESERVED = 4


class Game:
    FPS = 60

    def __init__(self) -> None:
        pygame.init()

        # from cursor import cursor_zero, cursor_zero_surface
        # pygame.mouse.set_cursor(cursor_zero)

        pygame.display.set_caption("Real-time Chilmok, or Omok")  # 창 제목 설정
        self.displaysurf = pygame.display.set_mode((875, 1075))
        self.clock = pygame.time.Clock()
        self.background = pygame.image.load("board-PIL.png")
        self.dotum = pygame.font.SysFont("dotum", 30)
        self.black_heuk = self.dotum.render("흑", True, (0, 0, 0))
        self.white_baek = self.dotum.render("백", True, (255, 255, 255))

        self.board = Board(self)
        self.black_gauge = 0.0
        self.white_gauge = 0.0

        self.displaysurf.blit(self.background, (0, 0))

    def loop(self):
        mouse_over_shadow = pygame.Surface((51, 51), pygame.SRCALPHA)
        mouse_over_shadow.fill((255, 255, 255, 0))  # RGBA : totally transparent
        mouse_over_shadow.set_alpha(128)
        while True:
            # 고정된 그림: 백 점수판, 배경, 흑 점수판
            pygame.draw.rect(
                self.displaysurf,
                Color.BLACK.value,
                [(0, 0), (875, 100)]
            )
            self.displaysurf.blit(self.background, (0, 100))
            pygame.draw.rect(
                self.displaysurf,
                Color.WHITE.value,
                [(0, 975), (875, 100)]
            )

            # 마우스 이벤트
            for event in pygame.event.get():
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = pygame.mouse.get_pos()
                    target: Space = None
                    for row in self.board.spaces:
                        for space in row:
                            if space.rect.inflate(-10, -10).collidepoint(pos):
                                # print(space)
                                target = space
                                break
                        if target is not None:
                            break
                    if target is not None:
                        pressed = pygame.mouse.get_pressed()
                        if pressed[0]:  # 좌클릭
                            target.click(Team.BLACK)
                        elif pressed[2]:  # 우클릭
                            target.click(Team.WHITE)
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()
            
            # 마우스 hover 시 그림자 표시
            pos = pygame.mouse.get_pos()
            target: Space = None
            for row in self.board.spaces:
                for space in row:
                    if space.rect.inflate(-10, -10).collidepoint(pos):  # Taxi distance
                    # if pygame.Vector2(space.rect.center).distance_to(pos) < 25:  # Euclidean distance
                        target = space
                        break
                if target is not None:
                    break
            if target is not None:
                if target.state == State.EMPTY:
                    pygame.draw.circle(
                        mouse_over_shadow,
                        (127, 127, 127),
                        mouse_over_shadow.get_rect().center,
                        17, 0
                    )
                    self.displaysurf.blit(mouse_over_shadow, target.rect.topleft)

            # 점수판 표시
            black_5, white_5 = self.board.count_5_connected()
            black_score = self.dotum.render(f"{black_5}/3", True, (0, 0, 0))
            white_score = self.dotum.render(f"{white_5}/3", True, (255, 255, 255))
            self.displaysurf.blit(self.black_heuk, (75, 1010))
            self.displaysurf.blit(self.white_baek, (700, 35))
            self.displaysurf.blit(black_score, (125, 1010))
            self.displaysurf.blit(white_score, (750, 35))
            # from cursor import cursor_zero, cursor_zero_surface
            # self.displaysurf.blit(cursor_zero_surface, (200, 200))

            # 게이지 표시
            if self.black_gauge < 3:
                self.black_gauge += 1/240
            if self.white_gauge < 3:
                self.white_gauge += 1/240
            self.draw_gauge()

            if black_5 >= 3:
                print("Black wins!")
                break
            elif white_5 >= 3:
                print("White wins!")
                break

            self.board.update()
            pygame.display.update()
            self.clock.tick(Game.FPS)

    def draw_gauge(self):
        # 기본 돌 3개
        for i in range(3):
            pygame.draw.circle(
                self.displaysurf,
                (0, 0, 0),
                (250 + 40*i, 1025),
                20
            )
            pygame.draw.circle(
                self.displaysurf,
                (255, 255, 255),
                (400 + 40*i, 50),
                20
            )
        # 가리개를 통해 원의 일부를 가려서 활꼴을 그린다
        pygame.draw.rect(
            self.displaysurf,
            (255, 255, 255),
            (230 + self.black_gauge * 40, 1000, (3.0 - self.black_gauge) * 40 + 10, 50)
        )
        pygame.draw.rect(
            self.displaysurf,
            (0, 0, 0),
            (380 + self.white_gauge * 40, 25, (3.0 - self.white_gauge) * 40 + 10, 50)
        )


class Board:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.spaces = [[Space(self, j, i) for j in range(15)] for i in range(15)]

    def update(self) -> None:
        for row in self.spaces:
            for space in row:
                try:
                    next(space.animation.play())
                except StopIteration as e:
                    if isinstance(space.animation, StoneReservedAnimation):
                        space.animation = StoneDeployedAnimation(space)
                    elif isinstance(space.animation, StoneDeployedAnimation):
                        space.animation = StoneIdleAnimation(space)

    def count_5_connected(self) -> tuple[int, int]:
        # 참고로 6목은 5목 2개로 본다.
        black_5 = 0
        white_5 = 0
        for row in self.spaces:
            for space in row:
                for team in [space.is_horizontal_5(), space.is_vertical_5(), space.is_slash_5(), space.is_backslash_5()]:
                    if team == Team.BLACK: black_5 += 1
                    elif team == Team.WHITE: white_5 += 1
        return black_5, white_5


class Space:
    def __init__(self, board: Board, x, y) -> None:
        self.board = board
        self.x = x  # 0-14
        self.y = y  # 0-14
        self.team = Team.NONE
        # self.team = Team.BLACK
        self.animation = SpaceAnimation(self)
        # self.animation = StoneIdleAnimation(self)

    def __repr__(self) -> str:
        row = str(15 - self.y)
        col = "ABCDEFGHIJKLMNOP"[self.x]
        return f"Space('{col}{row}')"

    @property
    def rect(self) -> Rect:
        return pygame.Rect(56 + 51 * self.x, 156 + 51 * self.y, 51, 51)

    @property
    def state(self) -> State:
        if isinstance(self.animation, SpaceAnimation):
            return State.EMPTY
        elif isinstance(self.animation, (StoneIdleAnimation, StoneDeployedAnimation)):
            if self.team == Team.BLACK:
                return State.BLACK
            elif self.team == Team.WHITE:
                return State.WHITE
            else:
                raise ValueError()
        elif isinstance(self.animation, StoneReservedAnimation):
            if self.team == Team.BLACK:
                return State.BLACK_RESERVED
            elif self.team == Team.WHITE:
                return State.WHITE_RESERVED
            else:
                raise ValueError()

    def click(self, team: Team):
        if self.state == State.EMPTY:
            if team == Team.BLACK:
                if self.board.game.black_gauge >= 1.0:
                    self.team = Team.BLACK
                    self.animation = StoneReservedAnimation(self)
                    self.board.game.black_gauge -= 1.0
            elif team == Team.WHITE:
                if self.board.game.white_gauge >= 1.0:
                    self.team = Team.WHITE
                    self.animation = StoneReservedAnimation(self)
                    self.board.game.white_gauge -= 1.0

        elif self.state == State.BLACK_RESERVED:
            if team == Team.BLACK:  # 흑 확정
                if self.board.game.black_gauge >= 1.0:
                    self.animation = StoneDeployedAnimation(self)
                    self.board.game.black_gauge -= 1.0
            elif team == Team.WHITE:  # 백 새치기
                if self.board.game.white_gauge >= 1.5:
                    if self.animation.current_frame > 15:
                        self.team = team
                        self.animation = StoneDeployedAnimation(self)
                        self.board.game.white_gauge -= 1.5
                        self.board.game.black_gauge = min(3.0, self.board.game.black_gauge + 1.0)

        elif self.state == State.WHITE_RESERVED:
            if team == Team.WHITE:  # 백 확정
                if self.board.game.white_gauge >= 1.0:
                    self.animation = StoneDeployedAnimation(self)
                    self.board.game.white_gauge -= 1.0
            elif team == Team.BLACK:  # 흑 새치기
                if self.board.game.black_gauge >= 1.5:
                    if self.animation.current_frame > 15:
                        self.team = team
                        self.animation = StoneDeployedAnimation(self)
                        self.board.game.black_gauge -= 1.5
                        self.board.game.white_gauge = min(3.0, self.board.game.white_gauge + 1.0)

    def is_horizontal_5(self) -> Team:
        if not 2 <= self.x <= 12:
            return Team.NONE
        if self.state not in [State.BLACK, State.WHITE]:
            return Team.NONE
        if self.board.spaces[self.y][self.x - 2].state \
            == self.board.spaces[self.y][self.x - 1].state \
            == self.state \
            == self.board.spaces[self.y][self.x + 1].state \
            == self.board.spaces[self.y][self.x + 2].state:
            return self.team
        else:
            return Team.NONE

    def is_vertical_5(self) -> Team:
        if not 2 <= self.y <= 12:
            return Team.NONE
        if self.state not in [State.BLACK, State.WHITE]:
            return Team.NONE
        if self.board.spaces[self.y - 2][self.x].state \
            == self.board.spaces[self.y - 1][self.x].state \
            == self.state \
            == self.board.spaces[self.y + 1][self.x].state \
            == self.board.spaces[self.y + 2][self.x].state:
            return self.team
        else:
            return Team.NONE

    def is_slash_5(self) -> Team:
        if (not 2 <= self.x <= 12) or (not 2 <= self.y <= 12):
            return Team.NONE
        if self.state not in [State.BLACK, State.WHITE]:
            return Team.NONE
        if self.board.spaces[self.y - 2][self.x + 2].state \
            == self.board.spaces[self.y - 1][self.x + 1].state \
            == self.state \
            == self.board.spaces[self.y + 1][self.x - 1].state \
            == self.board.spaces[self.y + 2][self.x - 2].state:
            return self.team
        else:
            return Team.NONE

    def is_backslash_5(self) -> Team:
        if (not 2 <= self.x <= 12) or (not 2 <= self.y <= 12):
            return Team.NONE
        if self.state not in [State.BLACK, State.WHITE]:
            return Team.NONE
        if self.board.spaces[self.y - 2][self.x - 2].state \
            == self.board.spaces[self.y - 1][self.x - 1].state \
            == self.state \
            == self.board.spaces[self.y + 1][self.x + 1].state \
            == self.board.spaces[self.y + 2][self.x + 2].state:
            return self.team
        else:
            return Team.NONE


if __name__ == '__main__':
    Game().loop()

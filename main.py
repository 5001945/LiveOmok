import os
import sys

import pygame

from code.omok3 import omok3
from code.network.udp import client_udp

class Lobby:
    FPS = 30

    def __init__(self) -> None:
        os.environ['SDL_VIDEO_WINDOW_POS'] = "300,30"  # 화면의 시작 위치

        pygame.init()
        self.clock = pygame.time.Clock()

        pygame.display.set_caption("Omok3 Lobby")  # 창 제목 설정
        self.displaysurf = pygame.display.set_mode((640, 480))
        self.singleplay_btn = pygame.Rect(100, 60, 440, 150)
        self.multiplay_btn = pygame.Rect(100, 270, 440, 150)

        self.dotum = pygame.font.SysFont("malgun gothic", 30)

    def loop(self) -> None:
        while True:
            self.displaysurf.fill((0, 0, 0))
            pygame.draw.rect(
                self.displaysurf,
                (127, 127, 127),
                self.singleplay_btn
            )
            pygame.draw.rect(
                self.displaysurf,
                (127, 127, 127),
                self.multiplay_btn
            )
            singleplay_text = self.dotum.render("연습 게임", True, (0, 0, 0))
            multiplay_text = self.dotum.render("통신 플레이", True, (0, 0, 0))
            self.displaysurf.blit(singleplay_text, (140, 115))
            self.displaysurf.blit(multiplay_text, (140, 335))

            for event in pygame.event.get():
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = pygame.mouse.get_pos()
                    if self.singleplay_btn.collidepoint(pos):
                        self.do_singleplay()
                        # pygame.display.get_surface().
                        print("현재는 멀티플레이를 임시로 비활성화한 상태입니다.")
                        # pygame.quit()
                        # sys.exit()
                        self.displaysurf = pygame.display.set_mode((640, 480))
                    elif self.multiplay_btn.collidepoint(pos):
                        self.do_multiplay()
                        self.displaysurf = pygame.display.set_mode((640, 480))
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            pygame.display.update()
            self.clock.tick(Lobby.FPS)

    def do_singleplay(self):
        self.game = omok3.Game()
        winner = self.game.loop()
        print(winner)
        

    def do_multiplay(self):
        self.displaysurf.fill((0, 0, 0))
        wait_text = self.dotum.render("상대를 찾고 있습니다. 잠시 기다려주세요...", True, (0, 0, 0))
        self.displaysurf.blit(wait_text, (140, 115))
        pygame.display.update()

        udp = client_udp.OmokUDP()
        self.game = omok3.Game(multiplay=True, udp=udp)
        self.game.loop()


if __name__ == '__main__':
    Lobby().loop()

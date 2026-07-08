import json
import os
import sys

import pygame

from code.omok3 import omok3
from code.network.udp import client_udp


SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
DEFAULT_SETTINGS = {
    "multiplay_stone_color": "any",
    "nickname": "Player",
}
VALID_STONE_COLORS = {"black", "white", "any"}


class Lobby:
    FPS = 30

    def __init__(self) -> None:
        os.environ['SDL_VIDEO_WINDOW_POS'] = "300,30"  # 화면의 시작 위치

        pygame.init()
        self.clock = pygame.time.Clock()

        pygame.display.set_caption("Omok3 Lobby")  # 창 제목 설정
        self.displaysurf = pygame.display.set_mode((640, 480))
        self.singleplay_btn = pygame.Rect(100, 45, 440, 105)
        self.multiplay_btn = pygame.Rect(100, 185, 440, 105)
        self.settings_btn = pygame.Rect(100, 325, 440, 105)
        self.settings = self.load_settings()
        self.multiplay_stone_color = self.settings["multiplay_stone_color"]
        self.nickname = self.settings["nickname"]
        self.stone_color_labels = {
            "black": "흑",
            "white": "백",
            "any": "상관없음",
        }

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
            pygame.draw.rect(
                self.displaysurf,
                (127, 127, 127),
                self.settings_btn
            )
            singleplay_text = self.dotum.render("연습 게임", True, (0, 0, 0))
            multiplay_text = self.dotum.render("통신 플레이", True, (0, 0, 0))
            settings_text = self.dotum.render("설정", True, (0, 0, 0))
            self.displaysurf.blit(singleplay_text, (140, 77))
            self.displaysurf.blit(multiplay_text, (140, 217))
            self.displaysurf.blit(settings_text, (140, 357))

            for event in pygame.event.get():
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = pygame.mouse.get_pos()
                    if self.singleplay_btn.collidepoint(pos):
                        self.do_singleplay()
                        self.displaysurf = pygame.display.set_mode((640, 480))
                    elif self.multiplay_btn.collidepoint(pos):
                        mode, password = self.select_multiplay_mode()
                        if mode is not None:
                            self.do_multiplay(mode, password)
                        self.displaysurf = pygame.display.set_mode((640, 480))
                    elif self.settings_btn.collidepoint(pos):
                        self.open_settings()
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            pygame.display.update()
            self.clock.tick(Lobby.FPS)

    def do_singleplay(self):
        self.game = omok3.Game()
        winner = self.game.loop()
        print(winner)

    def load_settings(self) -> dict[str, str]:
        if not os.path.exists(SETTINGS_FILE):
            self.save_settings(DEFAULT_SETTINGS)
            return DEFAULT_SETTINGS.copy()

        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, json.JSONDecodeError):
            settings = {}

        if not isinstance(settings, dict):
            settings = {}

        merged = DEFAULT_SETTINGS.copy()
        stone_color = settings.get("multiplay_stone_color")
        if stone_color in VALID_STONE_COLORS:
            merged["multiplay_stone_color"] = stone_color
        nickname = settings.get("nickname")
        if isinstance(nickname, str) and nickname.strip():
            merged["nickname"] = nickname.strip()[:16]
        self.save_settings(merged)
        return merged

    def save_settings(self, settings: dict[str, str] | None = None) -> None:
        settings_to_save = settings or {
            "multiplay_stone_color": self.multiplay_stone_color,
            "nickname": self.nickname,
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings_to_save, f, ensure_ascii=False, indent=2)

    def open_settings(self) -> None:
        nickname_btn = pygame.Rect(100, 70, 440, 55)
        option_buttons = [
            ("black", pygame.Rect(100, 180, 440, 55)),
            ("white", pygame.Rect(100, 250, 440, 55)),
            ("any", pygame.Rect(100, 320, 440, 55)),
        ]
        back_btn = pygame.Rect(100, 400, 440, 50)

        while True:
            self.displaysurf.fill((0, 0, 0))
            title = self.dotum.render("설정", True, (255, 255, 255))
            color_title = self.dotum.render("멀티플레이 시 돌 색", True, (255, 255, 255))
            self.displaysurf.blit(title, (100, 20))
            self.displaysurf.blit(color_title, (100, 130))

            pygame.draw.rect(self.displaysurf, (127, 127, 127), nickname_btn)
            nickname_text = self.dotum.render(f"닉네임: {self.nickname}", True, (0, 0, 0))
            self.displaysurf.blit(nickname_text, (120, 77))

            for value, button in option_buttons:
                selected = value == self.multiplay_stone_color
                color = (210, 210, 210) if selected else (127, 127, 127)
                pygame.draw.rect(self.displaysurf, color, button)
                label = self.stone_color_labels[value]
                if selected:
                    label = label + "  *"
                text = self.dotum.render(label, True, (0, 0, 0))
                self.displaysurf.blit(text, (140, button.y + 8))

            pygame.draw.rect(self.displaysurf, (127, 127, 127), back_btn)
            back_text = self.dotum.render("뒤로 가기", True, (0, 0, 0))
            self.displaysurf.blit(back_text, (140, 406))

            for event in pygame.event.get():
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = pygame.mouse.get_pos()
                    if nickname_btn.collidepoint(pos):
                        nickname = self.ask_text("닉네임을 입력하세요.", self.nickname, 16)
                        if nickname:
                            self.nickname = nickname
                            self.settings["nickname"] = nickname
                            self.save_settings()
                    for value, button in option_buttons:
                        if button.collidepoint(pos):
                            self.multiplay_stone_color = value
                            self.settings["multiplay_stone_color"] = value
                            self.save_settings()
                    if back_btn.collidepoint(pos):
                        return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            pygame.display.update()
            self.clock.tick(Lobby.FPS)

    def ask_text(self, title_text: str, initial_text: str = "", max_length: int = 32) -> str | None:
        text_value = initial_text
        while True:
            self.displaysurf.fill((0, 0, 0))
            title = self.dotum.render(title_text, True, (255, 255, 255))
            guide = self.dotum.render("Enter: 확인 / Esc: 취소", True, (180, 180, 180))
            value_text = self.dotum.render(text_value or " ", True, (0, 0, 0))
            input_rect = pygame.Rect(100, 210, 440, 70)

            pygame.draw.rect(self.displaysurf, (255, 255, 255), input_rect)
            self.displaysurf.blit(title, (100, 115))
            self.displaysurf.blit(value_text, (120, 225))
            self.displaysurf.blit(guide, (150, 320))

            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        return text_value.strip() or None
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key == pygame.K_BACKSPACE:
                        text_value = text_value[:-1]
                    elif len(text_value) < max_length and event.unicode.isprintable():
                        text_value += event.unicode
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            pygame.display.update()
            self.clock.tick(Lobby.FPS)
        

    def select_multiplay_mode(self) -> tuple[str | None, str | None]:
        quick_btn = pygame.Rect(100, 60, 440, 120)
        friend_btn = pygame.Rect(100, 210, 440, 120)
        back_btn = pygame.Rect(100, 360, 440, 80)

        while True:
            self.displaysurf.fill((0, 0, 0))
            for button in (quick_btn, friend_btn, back_btn):
                pygame.draw.rect(self.displaysurf, (127, 127, 127), button)

            quick_text = self.dotum.render("빠른 대전", True, (0, 0, 0))
            friend_text = self.dotum.render("친구와 대전", True, (0, 0, 0))
            back_text = self.dotum.render("뒤로 가기", True, (0, 0, 0))
            self.displaysurf.blit(quick_text, (140, 100))
            self.displaysurf.blit(friend_text, (140, 250))
            self.displaysurf.blit(back_text, (140, 380))

            for event in pygame.event.get():
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = pygame.mouse.get_pos()
                    if quick_btn.collidepoint(pos):
                        return "quick", None
                    if friend_btn.collidepoint(pos):
                        password = self.ask_friend_password()
                        if password:
                            return "friend", password
                    if back_btn.collidepoint(pos):
                        return None, None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None, None
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            pygame.display.update()
            self.clock.tick(Lobby.FPS)

    def ask_friend_password(self) -> str | None:
        return self.ask_text("친구와 함께 사용할 암호를 입력하세요.", "", 32)

    def do_multiplay(self, mode: str = "quick", password: str | None = None):
        self.displaysurf.fill((0, 0, 0))
        wait_text = self.dotum.render("상대를 찾고 있습니다. 잠시 기다려주세요...", True, (255, 255, 255))
        self.displaysurf.blit(wait_text, (30, 210))
        pygame.display.update()

        udp = client_udp.OmokUDP(mode=mode, password=password, nickname=self.nickname)
        self.game = omok3.Game(
            multiplay=True,
            udp=udp,
            visual_team_preference=self.multiplay_stone_color,
            local_nickname=self.nickname,
        )
        self.game.loop()


if __name__ == '__main__':
    Lobby().loop()

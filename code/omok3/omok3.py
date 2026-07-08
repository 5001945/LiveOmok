import hashlib
import json
import sys
import os.path
import threading
from enum import Enum
from typing import Any, TYPE_CHECKING, Optional, Union

import pygame
from pygame import gfxdraw
from pygame.locals import *

from code.omok3.animations import SpaceAnimation, StoneDeployedAnimation, StoneIdleAnimation, StoneReservedAnimation
from code.network.udp.client_udp import OmokUDP


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

    def opponent(self) -> 'Team':
        if self == Team.BLACK:
            return Team.WHITE
        if self == Team.WHITE:
            return Team.BLACK
        raise ValueError()

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


class Validity(Enum):
    INVALID = 0
    RESERVE = 1  # 예약
    DENY = 2     # 새치기
    CONFIRM = 3  # 확정

RESERVE_COST = 1.0
CONFIRM_COST = 0.5
DENY_COST = 2.0
SYNC_CHECK_INTERVAL = 2000

class Game:
    FPS = 60

    def __init__(
        self,
        multiplay=False,
        udp: OmokUDP = None,
        visual_team_preference: str = "any",
        local_nickname: str = "Player",
    ) -> None:
        self.multiplay = multiplay
        self.local_team = Team.BLACK
        self.opponent_team = Team.WHITE
        self.visual_team_preference = visual_team_preference
        self.local_nickname = local_nickname
        self.opponent_nickname = "Opponent"
        self.server_role = "black"
        self.peer_role = "white"
        self.board_version = 0
        self.last_sync_check_at = 0
        self.opponent_moves: list[tuple[int, int]] = []
        self.pending_snapshot: dict[str, Any] | None = None
        self.network_lock = threading.Lock()
        self.network_result: str | None = None
        if self.multiplay:
            self.udp = udp
            self.opponent_nickname = self.udp.peer_nickname
            self.server_role = self.udp.role
            self.peer_role = "white" if self.server_role == "black" else "black"
            server_team = Team.WHITE if self.udp.role == "white" else Team.BLACK
            if self.visual_team_preference == "black":
                self.local_team = Team.BLACK
            elif self.visual_team_preference == "white":
                self.local_team = Team.WHITE
            else:
                self.local_team = server_team
            self.opponent_team = self.local_team.opponent()
            self.udp.rx_event = lambda data: self.decode_udp_and_update(data)
            self.udp.status_event = lambda data: self.handle_udp_status(data)
            self.udp.start_listen()
            self.opponent_chat: str = ""

        pygame.init()
        self.clock = pygame.time.Clock()
        
        pygame.mouse.set_visible(False)
        self.mouse_clicking = False

        pygame.display.set_caption("LiveOmok3")  # 창 제목 설정
        self.displaysurf = pygame.display.set_mode((875, 1075))
        root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # LiveOmok/
        img_path = os.path.join(root, "res", "board-PIL-step.png")  # LiveOmok/res/board-PIL-step.png
        self.background = pygame.image.load(img_path)
        self.dotum = pygame.font.SysFont("malgun gothic", 30)
        self.panel_font = pygame.font.SysFont("malgun gothic", 24)
        # self.dotum = pygame.font.SysFont("dotumche", 30)
        self.black_heuk = self.dotum.render("흑", True, Team.WHITE.color())
        self.white_baek = self.dotum.render("백", True, Team.BLACK.color())

        self.board = Board(self)
        self.black_gauge = 0.0
        self.white_gauge = 0.0

        self.displaysurf.blit(self.background, (0, 0))


    def event_lclick(self, click_pos: tuple[int, int]):
        target = self.find_mouse_pointed_space(click_pos)
        if (target is not None) and (target.valid(self.local_team) != Validity.INVALID):
            target.click(self.local_team)
            self.board_version += 1
            if self.multiplay:
                self.encode_udp_and_send(click_pos)


    def event_rclick(self, click_pos: tuple[int, int]):
        if self.multiplay:
            target = self.find_mouse_pointed_space(click_pos)
            if (self.gauge(self.local_team) >= RESERVE_COST + CONFIRM_COST) and (target is not None) and (target.valid(self.local_team) == Validity.RESERVE):
                target.click(self.local_team)
                self.encode_udp_and_send(click_pos)
            if (self.gauge(self.local_team) >= CONFIRM_COST) and (target is not None) and (target.valid(self.local_team) == Validity.CONFIRM):
                target.click(self.local_team)
                self.encode_udp_and_send(click_pos)
        else:
            target = self.find_mouse_pointed_space(click_pos)
            if (target is not None) and (target.valid(self.opponent_team) != Validity.INVALID):
                target.click(self.opponent_team)


    def loop(self) -> str:
        mouse_over_shadow = pygame.Surface((51, 51), pygame.SRCALPHA)
        mouse_over_shadow.fill((255, 255, 255, 0))  # RGBA : totally transparent
        mouse_over_shadow.set_alpha(128)
        cursor_with_gauge = pygame.Surface((41, 41), pygame.SRCALPHA)

        if self.multiplay:
            self.show_match_intro()

        while True:
            # 고정된 그림: 백 점수판, 배경, 흑 점수판
            pygame.draw.rect(
                self.displaysurf,
                self.opponent_team.color(),
                [(0, 0), (875, 100)]
            )
            self.displaysurf.blit(self.background, (0, 100))
            pygame.draw.rect(
                self.displaysurf,
                self.local_team.color(),
                [(0, 975), (875, 100)]
            )

            # 마우스 이벤트
            for event in pygame.event.get():
                left_clicked = pygame.mouse.get_pressed()[0]
                if event.type == pygame.MOUSEBUTTONDOWN and left_clicked:
                    if self.mouse_clicking:  # mouse holding
                        continue
                    self.mouse_clicking = True
                    pos = pygame.mouse.get_pos()
                    self.event_lclick(pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and pygame.mouse.get_pressed()[2]:
                    pos = pygame.mouse.get_pos()
                    self.event_rclick(pos)
                elif event.type == pygame.MOUSEBUTTONUP and not left_clicked:
                    self.mouse_clicking = False
                if event.type == QUIT:
                    if self.multiplay:
                        self.udp.close()
                    pygame.quit()
                    sys.exit()
            
            # UDP 이벤트(넷 플레이에서만)
            if self.multiplay:
                self.apply_pending_snapshot()
                self.send_periodic_sync_check()

                if self.network_result is not None:
                    pygame.mouse.set_visible(True)
                    self.udp.close(notify=False)
                    self.show_result_screen(self.network_result)
                    return self.network_result

                while True:
                    with self.network_lock:
                        if not self.opponent_moves:
                            break
                        opponent_move = self.opponent_moves.pop(0)
                    target = self.find_mouse_pointed_space(opponent_move)
                    if target is not None:
                        target.click(self.opponent_team)
                        self.board_version += 1
            
            # 마우스 hover 시 그림자 표시
            pos = pygame.mouse.get_pos()
            target = self.find_mouse_pointed_space(pos)
            if target is not None:
                if target.state == State.EMPTY:
                    pygame.draw.circle(
                        mouse_over_shadow,
                        (127, 127, 127),
                        mouse_over_shadow.get_rect().center,
                        17
                    )
                    self.displaysurf.blit(mouse_over_shadow, target.rect.topleft)

            # 점수판 표시
            black_5, white_5 = self.board.count_5_connected()
            local_5, opponent_5 = (black_5, white_5) if self.local_team == Team.BLACK else (white_5, black_5)
            local_score = self.dotum.render(f"{local_5}/3", True, self.opponent_team.color())
            opponent_score = self.dotum.render(f"{opponent_5}/3", True, self.local_team.color())
            self.displaysurf.blit(local_score, (700, 1005))
            self.displaysurf.blit(opponent_score, (700, 30))
            if self.local_team == Team.BLACK:
                self.displaysurf.blit(self.black_heuk, (650, 1005))
                self.displaysurf.blit(self.white_baek, (650, 30))
            else:
                self.displaysurf.blit(self.black_heuk, (650, 30))
                self.displaysurf.blit(self.white_baek, (650, 1005))

            # 게이지 표시
            if self.black_gauge < 3.0:
                self.black_gauge += 1/180  # 3초에 하나씩 채워진다
            if self.white_gauge < 3.0:
                self.white_gauge += 1/180
            self.draw_gauge()
            if self.multiplay:
                self.draw_player_panel_labels()

            if black_5 >= 3:
                pygame.mouse.set_visible(True)
                result = self.result_message(Team.BLACK)
                self.show_result_screen(result)
                return result
            elif white_5 >= 3:
                pygame.mouse.set_visible(True)
                result = self.result_message(Team.WHITE)
                self.show_result_screen(result)
                return result

            self.board.update()
            self.draw_stealable_opponent_warnings()

            # 마우스 커서 표시
            local_gauge = self.gauge(self.local_team)
            cursor_with_gauge.fill((255, 255, 255, 0))  # RGBA : totally transparent
            gfxdraw.aatrigon(cursor_with_gauge, 20, 22, 14, 4, 26, 4, (0, 0, 255))
            gfxdraw.aatrigon(cursor_with_gauge, 20, 22, 38, 27, 33, 36, (0, 0, 255))
            gfxdraw.aatrigon(cursor_with_gauge, 20, 22, 7, 36, 2, 27, (0, 0, 255))
            if 0.0 <= local_gauge < 1.0:
                gfxdraw.filled_trigon(
                    cursor_with_gauge,
                    20, 22,
                    round(20 - 6 * local_gauge), round(22 - 18 * local_gauge),
                    round(20 + 6 * local_gauge), round(22 - 18 * local_gauge),
                    (0, 0, 255)
                )
            elif 1.0 <= local_gauge < 2.0:
                gfxdraw.filled_trigon(cursor_with_gauge, 20, 22, 14, 4, 26, 4, (0, 0, 255))
                gfxdraw.filled_trigon(
                    cursor_with_gauge,
                    20, 22,
                    round(20 + 18 * (local_gauge-1)), round(22 + 5 * (local_gauge-1)),
                    round(20 + 13 * (local_gauge-1)), round(22 + 14 * (local_gauge-1)),
                    (0, 0, 255)
                )
            elif 2.0 <= local_gauge < 3.0:
                gfxdraw.filled_trigon(cursor_with_gauge, 20, 22, 14, 4, 26, 4, (0, 0, 255))
                gfxdraw.filled_trigon(cursor_with_gauge, 20, 22, 38, 27, 33, 36, (0, 0, 255))
                gfxdraw.filled_trigon(
                    cursor_with_gauge,
                    20, 22,
                    round(20 - 13 * (local_gauge-2)), round(22 + 14 * (local_gauge-2)),
                    round(20 - 18 * (local_gauge-2)), round(22 + 5 * (local_gauge-2)),
                    (0, 0, 255)
                )
            else:  # local_gauge >= 3.0
                gfxdraw.filled_trigon(cursor_with_gauge, 20, 22, 14, 4, 26, 4, (0, 0, 255))
                gfxdraw.filled_trigon(cursor_with_gauge, 20, 22, 38, 27, 33, 36, (0, 0, 255))
                gfxdraw.filled_trigon(cursor_with_gauge, 20, 22, 7, 36, 2, 27, (0, 0, 255))
            if self.current_move_can_be_stolen():
                self.draw_cursor_warning(cursor_with_gauge)
            self.displaysurf.blit(cursor_with_gauge, (pos[0]-21, pos[1]-21))

            pygame.display.update()
            self.clock.tick(Game.FPS)

    def result_message(self, winner_team: Team) -> str:
        if not self.multiplay:
            return f"{self.team_label(winner_team)} 승리!"
        if winner_team == self.local_team:
            return "승리!"
        return "패배..."

    def show_result_screen(self, result_text: str) -> None:
        started_at = pygame.time.get_ticks()
        title_font = pygame.font.SysFont("malgun gothic", 72)
        guide_font = pygame.font.SysFont("malgun gothic", 28)
        can_leave_after = 2000

        while True:
            elapsed = pygame.time.get_ticks() - started_at
            ready_to_leave = elapsed >= can_leave_after

            for event in pygame.event.get():
                if event.type == QUIT:
                    if self.multiplay:
                        self.udp.close(notify=False)
                    pygame.quit()
                    sys.exit()
                if ready_to_leave and event.type == pygame.MOUSEBUTTONDOWN:
                    return

            self.displaysurf.fill((18, 18, 18))
            result_surface = title_font.render(result_text, True, (255, 255, 255))
            result_rect = result_surface.get_rect(center=(437, 470))
            self.displaysurf.blit(result_surface, result_rect)

            if ready_to_leave:
                guide_text = "아무 데나 클릭하면 메인 화면으로 돌아갑니다."
            else:
                guide_text = ""
            guide_surface = guide_font.render(guide_text, True, (180, 180, 180))
            guide_rect = guide_surface.get_rect(center=(437, 570))
            self.displaysurf.blit(guide_surface, guide_rect)

            pygame.display.update()
            self.clock.tick(Game.FPS)

    def show_match_intro(self) -> None:
        intro_started = pygame.time.get_ticks()
        intro_duration = 2000
        title_font = pygame.font.SysFont("malgun gothic", 46)
        info_font = pygame.font.SysFont("malgun gothic", 34)
        label_font = pygame.font.SysFont("malgun gothic", 24)

        while pygame.time.get_ticks() - intro_started < intro_duration:
            for event in pygame.event.get():
                if event.type == QUIT:
                    self.udp.close()
                    pygame.quit()
                    sys.exit()

            self.displaysurf.fill((0, 0, 0))
            top_rect = pygame.Rect(0, 0, 875, 537)
            bottom_rect = pygame.Rect(0, 538, 875, 537)
            pygame.draw.rect(self.displaysurf, self.opponent_team.color(), top_rect)
            pygame.draw.rect(self.displaysurf, self.local_team.color(), bottom_rect)
            pygame.draw.line(self.displaysurf, (160, 160, 160), (0, 537), (875, 537), 2)

            self.draw_intro_player(
                rect=top_rect,
                label="상대",
                nickname=self.opponent_nickname,
                team=self.opponent_team,
                title_font=title_font,
                info_font=info_font,
                label_font=label_font,
            )
            self.draw_intro_player(
                rect=bottom_rect,
                label="나",
                nickname=self.local_nickname,
                team=self.local_team,
                title_font=title_font,
                info_font=info_font,
                label_font=label_font,
            )

            vs_text = title_font.render("VS", True, (230, 40, 40))
            vs_rect = vs_text.get_rect(center=(437, 537))
            pygame.draw.circle(self.displaysurf, (245, 245, 245), vs_rect.center, 44)
            self.displaysurf.blit(vs_text, vs_rect)

            pygame.display.update()
            self.clock.tick(Game.FPS)

    def draw_intro_player(
        self,
        rect: pygame.Rect,
        label: str,
        nickname: str,
        team: Team,
        title_font: pygame.font.Font,
        info_font: pygame.font.Font,
        label_font: pygame.font.Font,
    ) -> None:
        text_color = Color.WHITE.value if team == Team.BLACK else Color.BLACK.value
        label_text = label_font.render(label, True, text_color)
        nickname_text = title_font.render(nickname, True, text_color)
        team_text = info_font.render(f"돌 색: {self.team_label(team)}", True, text_color)

        self.displaysurf.blit(label_text, label_text.get_rect(center=(rect.centerx, rect.centery - 70)))
        self.displaysurf.blit(nickname_text, nickname_text.get_rect(center=(rect.centerx, rect.centery - 10)))
        self.displaysurf.blit(team_text, team_text.get_rect(center=(rect.centerx, rect.centery + 55)))

    def team_label(self, team: Team) -> str:
        if team == Team.BLACK:
            return "흑"
        if team == Team.WHITE:
            return "백"
        return ""


    def draw_gauge(self):
        local_team_y = 1000
        opponent_team_y = 25
        # 기본 돌 3개 (새치기 시 돌려받는 걸 대비해 3개 더 그린다)
        for i in range(6):
            pygame.draw.circle(
                self.displaysurf,
                self.local_team.color(),
                (350 + 40*i, opponent_team_y + 25),
                20,
                2
            )
            pygame.draw.circle(
                self.displaysurf,
                self.opponent_team.color(),
                (350 + 40*i, local_team_y + 25),
                20,
                2
            )
        # 가리개를 통해 원의 일부를 가려서 활꼴을 그린다
        local_team_gauge = self.gauge(self.local_team)
        opponent_team_gauge = self.gauge(self.opponent_team)
        pygame.draw.rect(
            self.displaysurf,
            self.opponent_team.color(),
            (330 + opponent_team_gauge * 40, opponent_team_y, (3.0 - opponent_team_gauge) * 40 + 130, 50)
        )
        pygame.draw.rect(
            self.displaysurf,
            self.local_team.color(),
            (330 + local_team_gauge * 40, local_team_y, (3.0 - local_team_gauge) * 40 + 130, 50)
        )

    def draw_player_panel_labels(self) -> None:
        self.draw_player_panel_label(self.local_team, "나", self.local_nickname)
        self.draw_player_panel_label(self.opponent_team, "상대", self.opponent_nickname)

    def draw_player_panel_label(self, team: Team, relation: str, nickname: str) -> None:
        text_color = team.opponent().color()
        text = self.panel_font.render(f"{relation}: {nickname}", True, text_color)
        if team == self.local_team:
            self.displaysurf.blit(text, (75, 1008))
        elif team == self.opponent_team:
            self.displaysurf.blit(text, (75, 33))

    def send_periodic_sync_check(self) -> None:
        now = pygame.time.get_ticks()
        if now - self.last_sync_check_at < SYNC_CHECK_INTERVAL:
            return
        self.last_sync_check_at = now
        self.udp.send({
            "type": "sync_check",
            "board_hash": self.board_hash(),
            "board_version": self.board_version,
            "non_empty_count": self.non_empty_count(),
        }, reliable=False)

    def handle_sync_check(self, msg: dict[str, Any]) -> None:
        peer_hash = str(msg.get("board_hash", ""))
        if peer_hash == self.board_hash():
            return

        peer_version = int(msg.get("board_version", 0))
        peer_count = int(msg.get("non_empty_count", 0))
        local_count = self.non_empty_count()
        local_hash = self.board_hash()

        if peer_version > self.board_version:
            self.udp.send({"type": "snapshot_request"}, reliable=True)
        elif peer_version < self.board_version:
            self.send_snapshot()
        elif peer_count > local_count or (peer_count == local_count and peer_hash > local_hash):
            self.udp.send({"type": "snapshot_request"}, reliable=True)
        else:
            self.send_snapshot()

    def send_snapshot(self) -> None:
        self.udp.send({
            "type": "snapshot",
            "board_hash": self.board_hash(),
            "board_version": self.board_version,
            "non_empty_count": self.non_empty_count(),
            "snapshot": self.create_snapshot(),
        }, reliable=True)

    def apply_pending_snapshot(self) -> None:
        with self.network_lock:
            snapshot_msg = self.pending_snapshot
            self.pending_snapshot = None
        if snapshot_msg is None:
            return

        snapshot_hash = str(snapshot_msg.get("board_hash", ""))
        if snapshot_hash == self.board_hash():
            return

        snapshot_version = int(snapshot_msg.get("board_version", 0))
        snapshot_count = int(snapshot_msg.get("non_empty_count", 0))
        local_count = self.non_empty_count()
        local_hash = self.board_hash()
        should_apply = (
            snapshot_version > self.board_version
            or (
                snapshot_version == self.board_version
                and (
                    snapshot_count > local_count
                    or (snapshot_count == local_count and snapshot_hash > local_hash)
                )
            )
        )
        if should_apply:
            self.apply_snapshot(snapshot_msg["snapshot"])
            self.board_version = snapshot_version
            print("Network - snapshot applied")

    def create_snapshot(self) -> dict[str, Any]:
        return {
            "gauges": {
                self.server_role: self.gauge(self.local_team),
                self.peer_role: self.gauge(self.opponent_team),
            },
            "spaces": [
                [self.serialize_space(space) for space in row]
                for row in self.board.spaces
            ],
        }

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        gauges = snapshot.get("gauges", {})
        if isinstance(gauges, dict):
            if self.server_role in gauges:
                self.set_gauge(self.local_team, float(gauges[self.server_role]))
            if self.peer_role in gauges:
                self.set_gauge(self.opponent_team, float(gauges[self.peer_role]))
        spaces = snapshot.get("spaces", [])
        for y, row in enumerate(spaces):
            if y >= len(self.board.spaces) or not isinstance(row, list):
                continue
            for x, space_data in enumerate(row):
                if x >= len(self.board.spaces[y]) or not isinstance(space_data, dict):
                    continue
                self.apply_space_snapshot(self.board.spaces[y][x], space_data)

    def serialize_space(self, space: 'Space') -> dict[str, Any]:
        return {
            "owner_role": self.owner_role(space),
            "animation": self.animation_name(space),
            "frame": space.animation.current_frame,
        }

    def apply_space_snapshot(self, space: 'Space', space_data: dict[str, Any]) -> None:
        owner_role = space_data.get("owner_role")
        if owner_role == self.server_role:
            space.team = self.local_team
        elif owner_role == self.peer_role:
            space.team = self.opponent_team
        else:
            space.team = Team.NONE

        animation_name = space_data.get("animation")
        if animation_name == "reserved":
            space.animation = StoneReservedAnimation(space)
        elif animation_name == "deployed":
            space.animation = StoneDeployedAnimation(space)
        elif animation_name == "idle":
            space.animation = StoneIdleAnimation(space)
        else:
            space.animation = SpaceAnimation(space)

        max_frame = max(space.animation.total_frame, 1)
        space.animation.current_frame = max(0, min(int(space_data.get("frame", 0)), max_frame))

    def board_hash(self) -> str:
        payload = [
            [
                {
                    "owner_role": self.owner_role(space),
                    "state": space.state.name,
                }
                for space in row
            ]
            for row in self.board.spaces
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def non_empty_count(self) -> int:
        return sum(
            1
            for row in self.board.spaces
            for space in row
            if space.state != State.EMPTY
        )

    def owner_role(self, space: 'Space') -> str | None:
        if space.team == self.local_team:
            return self.server_role
        if space.team == self.opponent_team:
            return self.peer_role
        return None

    def animation_name(self, space: 'Space') -> str:
        if isinstance(space.animation, StoneReservedAnimation):
            return "reserved"
        if isinstance(space.animation, StoneDeployedAnimation):
            return "deployed"
        if isinstance(space.animation, StoneIdleAnimation):
            return "idle"
        return "empty"

    def gauge(self, team: Team) -> float:
        if team == Team.BLACK:
            return self.black_gauge
        if team == Team.WHITE:
            return self.white_gauge
        raise ValueError()

    def set_gauge(self, team: Team, value: float) -> None:
        value = max(0.0, min(3.0, value))
        if team == Team.BLACK:
            self.black_gauge = value
        elif team == Team.WHITE:
            self.white_gauge = value
        else:
            raise ValueError()

    def projected_gauge(self, team: Team, frames: int) -> float:
        gauge = self.gauge(team)
        if gauge >= 3.0:
            return gauge
        return min(3.0, gauge + frames / 180)

    def current_move_can_be_stolen(self) -> bool:
        opponent_gauge = self.projected_gauge(self.opponent_team, StoneReservedAnimation.TOTAL_FRAME)
        return opponent_gauge >= DENY_COST

    def draw_cursor_warning(self, cursor: pygame.Surface) -> None:
        pygame.draw.circle(cursor, (220, 25, 25), (33, 8), 7)
        pygame.draw.line(cursor, (255, 255, 255), (33, 4), (33, 9), 2)
        pygame.draw.circle(cursor, (255, 255, 255), (33, 12), 1)

    def draw_stealable_opponent_warnings(self) -> None:
        for row in self.board.spaces:
            for space in row:
                if not self.can_steal_when_reservation_ends(space):
                    continue
                center = (space.rect.centerx + 15, space.rect.centery - 15)
                pygame.draw.circle(self.displaysurf, (35, 170, 70), center, 8)
                pygame.draw.line(
                    self.displaysurf,
                    (255, 255, 255),
                    (center[0], center[1] - 5),
                    (center[0], center[1] + 1),
                    2,
                )
                pygame.draw.circle(self.displaysurf, (255, 255, 255), (center[0], center[1] + 5), 1)

    def can_steal_when_reservation_ends(self, space: 'Space') -> bool:
        if space.team != self.opponent_team:
            return False
        if not isinstance(space.animation, StoneReservedAnimation):
            return False

        remaining_frames = max(space.animation.total_frame - space.animation.current_frame, 0)
        local_gauge = self.projected_gauge(self.local_team, remaining_frames)
        return local_gauge >= DENY_COST


    def decode_udp_and_update(self, msg: dict[str, Any]) -> None:
        print(f"Opponent - {msg}")
        msg_type = msg.get("type")
        if msg_type == "move":
            with self.network_lock:
                self.opponent_moves.append((int(msg["x"]), int(msg["y"])))
        elif msg_type == "chat":
            self.opponent_chat = str(msg.get("message", ""))
            print(self.opponent_chat)
        elif msg_type == "leave":
            self.network_result = "승리!"
        elif msg_type == "sync_check":
            self.handle_sync_check(msg)
        elif msg_type == "snapshot_request":
            self.send_snapshot()
        elif msg_type == "snapshot":
            with self.network_lock:
                self.pending_snapshot = msg

    def handle_udp_status(self, msg: dict[str, Any]) -> None:
        print(f"Network - {msg}")
        if msg.get("type") == "opponent_disconnected":
            self.network_result = "승리!"

    def encode_udp_and_send(self, pos_or_msg: Union[tuple[int, int], str]) -> None:
        if isinstance(pos_or_msg, tuple):
            msg = {"type": "move", "x": pos_or_msg[0], "y": pos_or_msg[1]}
        elif isinstance(pos_or_msg, str):
            msg = {"type": "chat", "message": pos_or_msg}
        print(f"Me - {msg}")
        self.udp.send(msg)


    def find_mouse_pointed_space(self, pos: tuple[int, int]) -> Optional['Space']:
        target: Optional['Space'] = None
        for row in self.board.spaces:
            for space in row:
                if space.rect.inflate(-10, -10).collidepoint(pos):  # Taxi distance
                # if pygame.Vector2(space.rect.center).distance_to(pos) < 25:  # Euclidean distance
                    target = space
                    break
            if target is not None:
                break
        return target


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
        # 참고로 6목은 5목 2개로 본다. 7목은 5목 3개로 보기 때문에 바로 이긴다.
        black_5 = 0
        white_5 = 0
        for row in self.spaces:
            for space in row:
                for team in [space.is_horizontal_5(), space.is_vertical_5(), space.is_slash_5(), space.is_backslash_5()]:
                    if team == Team.BLACK: black_5 += 1
                    elif team == Team.WHITE: white_5 += 1
        return black_5, white_5


class Space:
    
    def __init__(self, board: Board, x: int, y: int) -> None:
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
    def rect(self) -> pygame.Rect:
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

    def valid(self, clicker_team: Team) -> Validity:
        if self.state == State.EMPTY:
            if (clicker_team == Team.BLACK and self.board.game.black_gauge >= RESERVE_COST) \
                or (clicker_team == Team.WHITE and self.board.game.white_gauge >= RESERVE_COST):
                return Validity.RESERVE
        elif self.state == State.BLACK_RESERVED:
            if (clicker_team == Team.BLACK and self.board.game.black_gauge >= CONFIRM_COST):
                return Validity.CONFIRM
            if (clicker_team == Team.WHITE and self.board.game.white_gauge >= DENY_COST):
                return Validity.DENY
        elif self.state == State.WHITE_RESERVED:
            if (clicker_team == Team.BLACK and self.board.game.black_gauge >= DENY_COST):
                return Validity.DENY
            if (clicker_team == Team.WHITE and self.board.game.white_gauge >= CONFIRM_COST):
                return Validity.CONFIRM
        else: return Validity.INVALID


    def click(self, clicker_team: Team):
        if self.state == State.EMPTY:
            if clicker_team == Team.BLACK:
                if self.board.game.black_gauge >= RESERVE_COST:
                    self.team = Team.BLACK
                    self.animation = StoneReservedAnimation(self)
                    self.board.game.black_gauge -= RESERVE_COST
            elif clicker_team == Team.WHITE:
                if self.board.game.white_gauge >= RESERVE_COST:
                    self.team = Team.WHITE
                    self.animation = StoneReservedAnimation(self)
                    self.board.game.white_gauge -= RESERVE_COST

        elif self.state == State.BLACK_RESERVED:
            if clicker_team == Team.BLACK:  # 흑 확정
                if self.board.game.black_gauge >= CONFIRM_COST:
                    self.animation = StoneDeployedAnimation(self)
                    self.board.game.black_gauge -= CONFIRM_COST
            elif clicker_team == Team.WHITE:  # 백 새치기
                if self.board.game.white_gauge >= DENY_COST:
                    if self.animation.current_frame > 15:
                        self.team = clicker_team
                        self.animation = StoneDeployedAnimation(self)
                        self.board.game.white_gauge -= DENY_COST
                        # self.board.game.black_gauge = min(3.0, self.board.game.black_gauge + 1.0)
                        self.board.game.black_gauge += RESERVE_COST

        elif self.state == State.WHITE_RESERVED:
            if clicker_team == Team.WHITE:  # 백 확정
                if self.board.game.white_gauge >= CONFIRM_COST:
                    self.animation = StoneDeployedAnimation(self)
                    self.board.game.white_gauge -= CONFIRM_COST
            elif clicker_team == Team.BLACK:  # 흑 새치기
                if self.board.game.black_gauge >= DENY_COST:
                    if self.animation.current_frame > 15:
                        self.team = clicker_team
                        self.animation = StoneDeployedAnimation(self)
                        self.board.game.black_gauge -= DENY_COST
                        # self.board.game.white_gauge = min(3.0, self.board.game.white_gauge + 1.0)
                        self.board.game.white_gauge += RESERVE_COST


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

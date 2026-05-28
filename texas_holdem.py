#!/usr/bin/env python3
"""本地多终端德州扑克命令行小游戏。"""

from __future__ import annotations

import argparse
import json
import random
import socket
import socketserver
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Any, Optional

HOST = "127.0.0.1"
PORT = 8765
STARTING_CHIPS = 1000
SMALL_BLIND = 10
BIG_BLIND = 20
MIN_PLAYERS = 2
MAX_PLAYERS = 9
RANKS = "23456789TJQKA"
SUITS = "SHDC"
RANK_VALUE = {rank: index + 2 for index, rank in enumerate(RANKS)}


class Action(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def text(self) -> str:
        return f"{self.rank}{self.suit}"


@dataclass
class Player:
    name: str
    conn: Optional[socket.socket]
    is_ai: bool = False
    chips: int = STARTING_CHIPS
    hand: list[Card] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    bet: int = 0
    total_bet: int = 0
    seat: int = -1

    def active(self) -> bool:
        return not self.folded and self.chips > 0

    def can_act(self) -> bool:
        return not self.folded and not self.all_in and self.chips > 0


class PokerGame:
    def __init__(self, host: str, port: int, expected_players: int, bots: int):
        if expected_players < MIN_PLAYERS or expected_players > MAX_PLAYERS:
            raise ValueError(f"玩家数必须在 {MIN_PLAYERS}-{MAX_PLAYERS} 之间")
        if bots < 0 or bots >= expected_players:
            raise ValueError("AI 数量必须小于总玩家数")
        self.host = host
        self.port = port
        self.expected_players = expected_players
        self.players: list[Player] = []
        self.lock = threading.Lock()
        self.started = threading.Event()
        self.finished = threading.Event()
        self.deck: list[Card] = []
        self.board: list[Card] = []
        self.dealer_index = -1
        self.hand_no = 0
        for index in range(bots):
            self.players.append(Player(name=f"AI-{index + 1}", conn=None, is_ai=True))

    def add_human(self, name: str, conn: socket.socket) -> tuple[bool, str]:
        with self.lock:
            if self.started.is_set():
                return False, "牌局已经开始"
            if len(self.players) >= self.expected_players:
                return False, "房间已满"
            safe_name = name.strip()[:20] or f"玩家{len(self.players) + 1}"
            if any(player.name == safe_name for player in self.players):
                return False, "昵称已存在"
            self.players.append(Player(name=safe_name, conn=conn))
            self.broadcast({"type": "info", "message": f"{safe_name} 加入房间，当前 {len(self.players)}/{self.expected_players}"})
            if len(self.players) == self.expected_players:
                self.started.set()
            return True, safe_name

    def run(self) -> None:
        print(f"服务端启动：{self.host}:{self.port}，等待 {self.expected_players} 名玩家")
        self.started.wait()
        for index, player in enumerate(self.players):
            player.seat = index
        self.broadcast({"type": "info", "message": "玩家已满，牌局开始"})
        while self.players_with_chips() > 1:
            self.play_hand()
            time.sleep(2)
        winner = next(player for player in self.players if player.chips > 0)
        self.broadcast({"type": "game_over", "message": f"游戏结束，{winner.name} 获胜"})
        self.finished.set()
        print(f"游戏结束，{winner.name} 获胜")

    def play_hand(self) -> None:
        self.hand_no += 1
        self.reset_hand()
        self.dealer_index = self.next_player_index(self.dealer_index)
        sb_index = self.next_player_index(self.dealer_index)
        bb_index = self.next_player_index(sb_index)
        self.post_blind(sb_index, SMALL_BLIND)
        self.post_blind(bb_index, BIG_BLIND)
        self.deal_hole_cards()
        self.broadcast_state("新一手开始")

        current = self.next_player_index(bb_index)
        if self.betting_round(current):
            self.finish_by_fold()
            return
        for count, stage in [(3, "翻牌"), (1, "转牌"), (1, "河牌")]:
            self.board.extend(self.draw(count))
            for player in self.players:
                player.bet = 0
            self.broadcast_state(stage)
            if self.betting_round(self.next_player_index(self.dealer_index)):
                self.finish_by_fold()
                return
        self.showdown()

    def reset_hand(self) -> None:
        self.deck = [Card(rank, suit) for rank in RANKS for suit in SUITS]
        random.shuffle(self.deck)
        self.board = []
        for player in self.players:
            player.hand.clear()
            player.folded = player.chips <= 0
            player.all_in = False
            player.bet = 0
            player.total_bet = 0

    def deal_hole_cards(self) -> None:
        for _ in range(2):
            for player in self.players:
                if player.chips > 0:
                    player.hand.extend(self.draw(1))

    def draw(self, count: int) -> list[Card]:
        cards = self.deck[:count]
        del self.deck[:count]
        return cards

    def post_blind(self, index: int, amount: int) -> None:
        player = self.players[index]
        paid = min(amount, player.chips)
        player.chips -= paid
        player.bet += paid
        player.total_bet += paid
        player.all_in = player.chips == 0
        self.broadcast({"type": "info", "message": f"{player.name} 下盲注 {paid}"})

    def betting_round(self, start_index: int) -> bool:
        current_bet = max(player.bet for player in self.players)
        acted: set[int] = set()
        index = start_index
        while True:
            if self.only_one_left():
                return True
            player = self.players[index]
            if player.can_act():
                to_call = current_bet - player.bet
                action, amount = self.get_action(player, to_call, current_bet)
                if action == Action.FOLD:
                    player.folded = True
                    self.broadcast({"type": "info", "message": f"{player.name} 弃牌"})
                elif action == Action.CHECK:
                    if to_call > 0:
                        self.apply_call(player, to_call)
                    else:
                        self.broadcast({"type": "info", "message": f"{player.name} 过牌"})
                elif action == Action.CALL:
                    self.apply_call(player, to_call)
                elif action == Action.RAISE:
                    min_raise = BIG_BLIND
                    target_bet = max(current_bet + min_raise, player.bet + to_call + amount)
                    added = min(target_bet - player.bet, player.chips)
                    player.chips -= added
                    player.bet += added
                    player.total_bet += added
                    player.all_in = player.chips == 0
                    current_bet = max(current_bet, player.bet)
                    acted = {index}
                    self.broadcast({"type": "info", "message": f"{player.name} 加注到 {player.bet}"})
                acted.add(index)
                self.broadcast_state("行动后状态")
            if self.round_complete(acted, current_bet):
                return False
            index = self.next_player_index(index)

    def apply_call(self, player: Player, to_call: int) -> None:
        paid = min(to_call, player.chips)
        player.chips -= paid
        player.bet += paid
        player.total_bet += paid
        player.all_in = player.chips == 0
        self.broadcast({"type": "info", "message": f"{player.name} 跟注 {paid}"})

    def get_action(self, player: Player, to_call: int, current_bet: int) -> tuple[Action, int]:
        if player.is_ai:
            return self.ai_action(player, to_call, current_bet)
        state = self.visible_state(player, f"轮到你行动，需要跟注 {to_call}")
        state["type"] = "your_turn"
        state["to_call"] = to_call
        state["min_raise"] = BIG_BLIND
        self.send(player, state)
        try:
            line = player.conn.recv(4096).decode("utf-8").strip() if player.conn else ""
            payload = json.loads(line)
            action = Action(payload.get("action", "fold"))
            amount = int(payload.get("amount", 0))
            if action == Action.CHECK and to_call > 0:
                action = Action.CALL
            if action == Action.RAISE and amount <= 0:
                action = Action.CALL
            return action, amount
        except Exception:
            return Action.FOLD, 0

    def ai_action(self, player: Player, to_call: int, current_bet: int) -> tuple[Action, int]:
        strength = estimate_strength(player.hand, self.board)
        time.sleep(0.6)
        if to_call == 0:
            if strength >= 0.72 and player.chips > BIG_BLIND:
                return Action.RAISE, min(BIG_BLIND * 2, player.chips)
            return Action.CHECK, 0
        pressure = to_call / max(player.chips + to_call, 1)
        if strength < 0.35 and pressure > 0.12:
            return Action.FOLD, 0
        if strength > 0.82 and player.chips > to_call + BIG_BLIND:
            return Action.RAISE, min(BIG_BLIND * 3, player.chips - to_call)
        return Action.CALL, 0

    def round_complete(self, acted: set[int], current_bet: int) -> bool:
        for index, player in enumerate(self.players):
            if player.can_act() and (index not in acted or player.bet != current_bet):
                return False
        return True

    def only_one_left(self) -> bool:
        return sum(1 for player in self.players if not player.folded and player.chips + player.total_bet > 0) == 1

    def finish_by_fold(self) -> None:
        winner = next(player for player in self.players if not player.folded)
        pot = sum(player.total_bet for player in self.players)
        winner.chips += pot
        self.broadcast_state(f"{winner.name} 赢得底池 {pot}")

    def showdown(self) -> None:
        contenders = [player for player in self.players if not player.folded]
        ranked = sorted(contenders, key=lambda player: evaluate_best(player.hand + self.board), reverse=True)
        winner = ranked[0]
        pot = sum(player.total_bet for player in self.players)
        winner.chips += pot
        cards = ", ".join(f"{player.name}: {' '.join(card.text() for card in player.hand)}" for player in contenders)
        self.broadcast_state(f"摊牌：{cards}。{winner.name} 赢得底池 {pot}")

    def next_player_index(self, index: int) -> int:
        for step in range(1, len(self.players) + 1):
            next_index = (index + step) % len(self.players)
            if self.players[next_index].chips > 0:
                return next_index
        return index

    def players_with_chips(self) -> int:
        return sum(1 for player in self.players if player.chips > 0)

    def visible_state(self, viewer: Player, message: str) -> dict[str, Any]:
        return {
            "type": "state",
            "message": message,
            "hand_no": self.hand_no,
            "board": [card.text() for card in self.board],
            "pot": sum(player.total_bet for player in self.players),
            "you": viewer.name,
            "hole": [card.text() for card in viewer.hand],
            "players": [
                {
                    "name": player.name,
                    "chips": player.chips,
                    "bet": player.bet,
                    "folded": player.folded,
                    "all_in": player.all_in,
                    "is_ai": player.is_ai,
                }
                for player in self.players
            ],
        }

    def broadcast_state(self, message: str) -> None:
        print(message)
        for player in self.players:
            if not player.is_ai:
                self.send(player, self.visible_state(player, message))

    def broadcast(self, payload: dict[str, Any]) -> None:
        print(payload.get("message", payload.get("type", "")))
        for player in self.players:
            if not player.is_ai:
                self.send(player, payload)

    def send(self, player: Player, payload: dict[str, Any]) -> None:
        if not player.conn:
            return
        try:
            player.conn.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            player.folded = True


def evaluate_best(cards: list[Card]) -> tuple[int, list[int]]:
    return max(evaluate_five(list(combo)) for combo in combinations(cards, 5))


def evaluate_five(cards: list[Card]) -> tuple[int, list[int]]:
    values = sorted((RANK_VALUE[card.rank] for card in cards), reverse=True)
    counts = {value: values.count(value) for value in set(values)}
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    flush = len({card.suit for card in cards}) == 1
    unique = sorted(set(values), reverse=True)
    if unique == [14, 5, 4, 3, 2]:
        straight_high = 5
    else:
        straight_high = unique[0] if len(unique) == 5 and unique[0] - unique[-1] == 4 else 0
    if straight_high and flush:
        return 8, [straight_high]
    if groups[0][1] == 4:
        return 7, [groups[0][0], groups[1][0]]
    if groups[0][1] == 3 and groups[1][1] == 2:
        return 6, [groups[0][0], groups[1][0]]
    if flush:
        return 5, values
    if straight_high:
        return 4, [straight_high]
    if groups[0][1] == 3:
        kickers = [value for value in values if value != groups[0][0]]
        return 3, [groups[0][0]] + kickers
    if groups[0][1] == 2 and groups[1][1] == 2:
        pair_values = sorted([groups[0][0], groups[1][0]], reverse=True)
        kicker = next(value for value in values if value not in pair_values)
        return 2, pair_values + [kicker]
    if groups[0][1] == 2:
        kickers = [value for value in values if value != groups[0][0]]
        return 1, [groups[0][0]] + kickers
    return 0, values


def estimate_strength(hand: list[Card], board: list[Card]) -> float:
    cards = hand + board
    if len(cards) >= 5:
        category, ranks = evaluate_best(cards)
        return min(0.98, category / 8 + ranks[0] / 100)
    first, second = sorted((RANK_VALUE[card.rank] for card in hand), reverse=True)
    suited = hand[0].suit == hand[1].suit
    pair_bonus = 0.35 if first == second else 0
    high_bonus = (first + second) / 35
    suited_bonus = 0.08 if suited else 0
    return min(0.95, 0.15 + pair_bonus + high_bonus + suited_bonus)


class JoinHandler(socketserver.BaseRequestHandler):
    game: PokerGame

    def handle(self) -> None:
        file = self.request.makefile("r", encoding="utf-8")
        try:
            hello = json.loads(file.readline())
            ok, name = self.game.add_human(str(hello.get("name", "")), self.request)
            if not ok:
                self.request.sendall((json.dumps({"type": "error", "message": name}, ensure_ascii=False) + "\n").encode("utf-8"))
                return
            self.request.sendall((json.dumps({"type": "joined", "name": name}, ensure_ascii=False) + "\n").encode("utf-8"))
            self.game.finished.wait()
        except Exception as exc:
            print(f"客户端连接异常：{exc}")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


def run_server(args: argparse.Namespace) -> None:
    game = PokerGame(args.host, args.port, args.players, args.bots)
    JoinHandler.game = game
    server = ThreadedTCPServer((args.host, args.port), JoinHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        game.run()
    finally:
        server.shutdown()
        server.server_close()


def run_client(args: argparse.Namespace) -> None:
    with socket.create_connection((args.host, args.port)) as sock:
        sock.sendall((json.dumps({"name": args.name}, ensure_ascii=False) + "\n").encode("utf-8"))
        file = sock.makefile("r", encoding="utf-8")
        for line in file:
            payload = json.loads(line)
            render_payload(payload)
            if payload.get("type") == "your_turn":
                action, amount = read_action(payload)
                sock.sendall((json.dumps({"action": action, "amount": amount}, ensure_ascii=False) + "\n").encode("utf-8"))
            if payload.get("type") == "game_over":
                return


def run_agent(args: argparse.Namespace) -> None:
    with socket.create_connection((args.host, args.port)) as sock:
        sock.sendall((json.dumps({"name": args.name}, ensure_ascii=False) + "\n").encode("utf-8"))
        file = sock.makefile("r", encoding="utf-8")
        for line in file:
            payload = json.loads(line)
            if payload.get("type") in {"info", "joined", "game_over"}:
                print(payload.get("message") or f"已加入：{payload.get('name')}")
            if payload.get("type") == "your_turn":
                action, amount = choose_agent_action(payload)
                print(f"AI 决策：{action} {amount}".strip())
                sock.sendall((json.dumps({"action": action, "amount": amount}, ensure_ascii=False) + "\n").encode("utf-8"))
            if payload.get("type") == "game_over":
                return


def render_payload(payload: dict[str, Any]) -> None:
    kind = payload.get("type")
    if kind in {"info", "joined", "error", "game_over"}:
        print(payload.get("message") or f"已加入：{payload.get('name')}")
        return
    print("\n" + "=" * 48)
    print(f"第 {payload.get('hand_no')} 手 | {payload.get('message')}")
    print(f"公共牌：{' '.join(payload.get('board', [])) or '-'} | 底池：{payload.get('pot')}")
    print(f"你的手牌：{' '.join(payload.get('hole', []))}")
    for player in payload.get("players", []):
        status = "弃牌" if player["folded"] else "全下" if player["all_in"] else "在局"
        marker = " <- 你" if player["name"] == payload.get("you") else ""
        print(f"{player['name']}: 筹码 {player['chips']} 本轮下注 {player['bet']} {status}{marker}")


def read_action(payload: dict[str, Any]) -> tuple[str, int]:
    to_call = int(payload.get("to_call", 0))
    prompt = "请选择行动 [f=弃牌, c=跟注, r 金额=加注"
    prompt += ", k=过牌" if to_call == 0 else ""
    prompt += "]: "
    while True:
        raw = input(prompt).strip().lower()
        if raw == "f":
            return "fold", 0
        if raw == "k" and to_call == 0:
            return "check", 0
        if raw in {"c", ""}:
            return "call", 0
        if raw.startswith("r"):
            parts = raw.split()
            amount = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else BIG_BLIND
            return "raise", amount
        print("输入无效，请重试")


def choose_agent_action(payload: dict[str, Any]) -> tuple[str, int]:
    hole = [parse_card(text) for text in payload.get("hole", [])]
    board = [parse_card(text) for text in payload.get("board", [])]
    to_call = int(payload.get("to_call", 0))
    chips = next((player["chips"] for player in payload.get("players", []) if player["name"] == payload.get("you")), STARTING_CHIPS)
    strength = estimate_strength(hole, board)
    pressure = to_call / max(chips + to_call, 1)
    if to_call == 0:
        if strength > 0.72 and chips > BIG_BLIND * 2:
            return "raise", BIG_BLIND * 2
        return "check", 0
    if strength < 0.38 and pressure > 0.15:
        return "fold", 0
    if strength > 0.84 and chips > to_call + BIG_BLIND * 2:
        return "raise", BIG_BLIND * 3
    return "call", 0


def parse_card(text: str) -> Card:
    return Card(text[0], text[1])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地多终端德州扑克小游戏")
    sub = parser.add_subparsers(dest="mode", required=True)
    server = sub.add_parser("server", help="启动服务端")
    server.add_argument("--host", default=HOST)
    server.add_argument("--port", type=int, default=PORT)
    server.add_argument("--players", type=int, default=4, help="总玩家数，包含 AI")
    server.add_argument("--bots", type=int, default=2, help="内置 AI 玩家数量")
    client = sub.add_parser("client", help="启动真人客户端")
    client.add_argument("--host", default=HOST)
    client.add_argument("--port", type=int, default=PORT)
    client.add_argument("--name", default="Human")
    agent = sub.add_parser("agent", help="启动独立 AI 客户端")
    agent.add_argument("--host", default=HOST)
    agent.add_argument("--port", type=int, default=PORT)
    agent.add_argument("--name", default="Agent")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "server":
        run_server(args)
    elif args.mode == "client":
        run_client(args)
    elif args.mode == "agent":
        run_agent(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

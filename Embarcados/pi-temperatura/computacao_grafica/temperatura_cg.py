"""
PI - Computacao Grafica
Visualizacao 3D da temperatura lida do ESP32.

Comunicacao (opcao 1 do enunciado): o programa faz uma requisicao HTTP para a
pagina do ESP32 e analisa o HTML com BeautifulSoup, lendo os elementos
<span id="c"> (temperatura em Celsius) e <span id="status"> (estado do cooler).

Modelagem:
  - Um cubo de gelo derrete (diminui de altura e largura) conforme a temperatura
    sobe e volta a crescer quando ela cai; uma poca d'agua cresce embaixo dele.
  - A cor do cubo muda conforme a faixa de temperatura.
  - Um cooler ao lado gira quando o ESP32 informa que o rele esta ligado,
    soprando ar (particulas) em direcao ao gelo.

Uso:
  python temperatura_cg.py --ip 192.168.0.50     (le do ESP32)
  python temperatura_cg.py --simular             (sem hardware, para testes)

Teclas: setas esquerda/direita giram a camera, ESC fecha.
"""

import argparse
import math
import random
import threading
import time

import pygame
import requests
from bs4 import BeautifulSoup
from OpenGL.GL import *

# Mesmos limiares do firmware (usados no modo simulado e na legenda)
TEMP_LIGAR = 28.0
TEMP_DESLIGAR = 27.0

# Faixas de cor do gelo: (limite superior da faixa, cor RGB, descricao)
FAIXAS = [
    (20.0, (0.70, 0.88, 1.00), "abaixo de 20 C"),
    (25.0, (0.45, 0.80, 0.95), "20 a 25 C"),
    (28.0, (0.95, 0.85, 0.35), "25 a 28 C"),
    (30.0, (1.00, 0.55, 0.20), "28 a 30 C"),
    (999.0, (0.90, 0.22, 0.15), "acima de 30 C"),
]

# Temperaturas em que o gelo esta inteiro e quase todo derretido
TEMP_GELO_INTEIRO = 20.0
TEMP_GELO_DERRETIDO = 32.0


# ---------------------------------------------------------------- fontes de dados

class FonteESP32:
    """Le a pagina do ESP32 em uma thread separada para nao travar a animacao."""

    def __init__(self, ip, intervalo=2.0):
        self.url = f"http://{ip}/"
        self.descricao = f"ESP32 em {ip}"
        self.intervalo = intervalo
        self._temperatura = None
        self._cooler = False
        self._erro = "Aguardando primeira leitura..."
        self._trava = threading.Lock()
        threading.Thread(target=self._laco, daemon=True).start()

    def _ler_pagina(self):
        resposta = requests.get(self.url, timeout=3)
        resposta.raise_for_status()
        sopa = BeautifulSoup(resposta.text, "html.parser")

        texto_c = sopa.find("span", id="c").get_text(strip=True)
        texto_status = sopa.find("span", id="status").get_text(strip=True)

        temperatura = None if texto_c in ("", "--") else float(texto_c)
        cooler = texto_status.upper() == "LIGADO"
        return temperatura, cooler

    def _laco(self):
        while True:
            try:
                temperatura, cooler = self._ler_pagina()
                erro = None if temperatura is not None else "ESP32 sem leitura do sensor"
                with self._trava:
                    self._temperatura, self._cooler, self._erro = temperatura, cooler, erro
            except Exception as exc:  # rede fora, IP errado, HTML inesperado
                with self._trava:
                    self._erro = f"Sem conexao com o ESP32 ({type(exc).__name__})"
            time.sleep(self.intervalo)

    def leitura(self):
        with self._trava:
            return self._temperatura, self._cooler, self._erro


class FonteSimulada:
    """Temperatura oscilando entre 21 e 32 C, com a mesma histerese do ESP32."""

    def __init__(self):
        self.descricao = "modo simulado"
        self.inicio = time.time()
        self.cooler = False

    def leitura(self):
        t = time.time() - self.inicio
        temperatura = 26.5 + 5.5 * math.sin(t / 6.0)
        if not self.cooler and temperatura > TEMP_LIGAR:
            self.cooler = True
        elif self.cooler and temperatura < TEMP_DESLIGAR:
            self.cooler = False
        return temperatura, self.cooler, None


# ---------------------------------------------------------------- utilitarios

def cor_da_faixa(temperatura):
    for limite, cor, _ in FAIXAS:
        if temperatura < limite:
            return cor
    return FAIXAS[-1][1]


def descricao_da_faixa(temperatura):
    for limite, _, texto in FAIXAS:
        if temperatura < limite:
            return texto
    return FAIXAS[-1][2]


def fracao_de_gelo(temperatura):
    """1.0 = gelo inteiro, 0.12 = quase todo derretido."""
    x = (temperatura - TEMP_GELO_INTEIRO) / (TEMP_GELO_DERRETIDO - TEMP_GELO_INTEIRO)
    x = max(0.0, min(1.0, x))
    return 1.0 - 0.88 * x


def aproximar(atual, alvo, velocidade, dt):
    return atual + (alvo - atual) * min(1.0, velocidade * dt)


# ---------------------------------------------------------------- camera

def perspectiva(fov_graus, aspecto, perto, longe):
    """Projecao perspectiva (mesmo efeito do gluPerspective), via glFrustum."""
    topo = perto * math.tan(math.radians(fov_graus) / 2)
    glFrustum(-topo * aspecto, topo * aspecto, -topo, topo, perto, longe)


def olhar_para(olho, alvo, cima=(0.0, 1.0, 0.0)):
    """Posiciona a camera em 'olho' mirando 'alvo' (mesmo efeito do gluLookAt)."""
    def normalizar(v):
        n = math.sqrt(sum(c * c for c in v))
        return [c / n for c in v]

    def vetorial(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    f = normalizar([alvo[i] - olho[i] for i in range(3)])
    s = normalizar(vetorial(f, cima))
    u = vetorial(s, f)
    matriz = [s[0], u[0], -f[0], 0,
              s[1], u[1], -f[1], 0,
              s[2], u[2], -f[2], 0,
              0, 0, 0, 1]
    glMultMatrixf(matriz)
    glTranslatef(-olho[0], -olho[1], -olho[2])


# ---------------------------------------------------------------- desenho

def caixa(sx, sy, sz):
    """Paralelepipedo centrado na origem, com normais para a iluminacao."""
    x, y, z = sx / 2, sy / 2, sz / 2
    faces = [
        ((0, 0, 1), [(-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]),
        ((0, 0, -1), [(-x, -y, -z), (-x, y, -z), (x, y, -z), (x, -y, -z)]),
        ((1, 0, 0), [(x, -y, -z), (x, y, -z), (x, y, z), (x, -y, z)]),
        ((-1, 0, 0), [(-x, -y, -z), (-x, -y, z), (-x, y, z), (-x, y, -z)]),
        ((0, 1, 0), [(-x, y, -z), (-x, y, z), (x, y, z), (x, y, -z)]),
        ((0, -1, 0), [(-x, -y, -z), (x, -y, -z), (x, -y, z), (-x, -y, z)]),
    ]
    glBegin(GL_QUADS)
    for normal, vertices in faces:
        glNormal3f(*normal)
        for v in vertices:
            glVertex3f(*v)
    glEnd()


def desenhar_piso():
    glColor4f(0.80, 0.81, 0.83, 1.0)
    glBegin(GL_QUADS)
    glNormal3f(0, 1, 0)
    glVertex3f(-6, 0, -6)
    glVertex3f(-6, 0, 6)
    glVertex3f(6, 0, 6)
    glVertex3f(6, 0, -6)
    glEnd()


def desenhar_poca(raio):
    glColor4f(0.35, 0.60, 0.90, 0.55)
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0, 1, 0)
    glVertex3f(0, 0.005, 0)
    for i in range(41):
        a = 2 * math.pi * i / 40
        glVertex3f(raio * math.cos(a), 0.005, raio * math.sin(a))
    glEnd()


def desenhar_gelo(fracao, cor):
    altura = 1.6 * fracao
    largura = 1.6 * (0.55 + 0.45 * fracao)
    glPushMatrix()
    glTranslatef(0, altura / 2 + 0.01, 0)
    glColor4f(cor[0], cor[1], cor[2], 0.85)
    caixa(largura, altura, largura)
    glPopMatrix()


def desenhar_cooler(angulo, ligado):
    """Cooler em pe, a direita do gelo, virado para ele."""
    glPushMatrix()
    glTranslatef(2.8, 1.0, 0)
    glRotatef(-90, 0, 1, 0)  # a frente do cooler aponta para o gelo (-x)

    # moldura quadrada
    glColor4f(0.22, 0.23, 0.25, 1.0)
    for dx, dy, sx, sy in [(0, 0.66, 1.44, 0.12), (0, -0.66, 1.44, 0.12),
                           (0.66, 0, 0.12, 1.44), (-0.66, 0, 0.12, 1.44)]:
        glPushMatrix()
        glTranslatef(dx, dy, 0)
        caixa(sx, sy, 0.3)
        glPopMatrix()

    # base ate o piso
    glPushMatrix()
    glTranslatef(0, -0.86, 0)
    caixa(0.5, 0.28, 0.5)
    glPopMatrix()

    # cubo central e pas
    caixa(0.24, 0.24, 0.2)
    if ligado:
        glColor4f(0.30, 0.55, 0.85, 1.0)
    else:
        glColor4f(0.60, 0.62, 0.65, 1.0)
    for i in range(5):
        glPushMatrix()
        glRotatef(angulo + i * 72, 0, 0, 1)
        glTranslatef(0, 0.36, 0)
        glRotatef(20, 0, 1, 0)  # inclinacao da pa
        caixa(0.2, 0.46, 0.03)
        glPopMatrix()
    glPopMatrix()


class Vento:
    """Particulas saindo do cooler em direcao ao gelo enquanto ele gira."""

    def __init__(self, quantidade=40):
        self.particulas = [self._nova(aleatorio_x=True) for _ in range(quantidade)]

    def _nova(self, aleatorio_x=False):
        x = random.uniform(0.9, 2.5) if aleatorio_x else 2.5
        return [x, random.uniform(0.45, 1.55), random.uniform(-0.55, 0.55)]

    def atualizar(self, dt, intensidade):
        for p in self.particulas:
            p[0] -= 2.2 * intensidade * dt
            if p[0] < 0.9:
                p[:] = self._nova()

    def desenhar(self, intensidade):
        if intensidade < 0.05:
            return
        glDisable(GL_LIGHTING)
        glPointSize(4)
        glBegin(GL_POINTS)
        for x, y, z in self.particulas:
            alfa = 0.7 * intensidade * (x - 0.9) / 1.6
            glColor4f(0.55, 0.75, 1.0, alfa)
            glVertex3f(x, y, z)
        glEnd()
        glEnable(GL_LIGHTING)


def desenhar_texto(fonte, x, y, texto, cor=(30, 30, 30)):
    """Desenha texto 2D na tela (x, y a partir do canto inferior esquerdo)."""
    superficie = fonte.render(texto, True, cor)
    dados = pygame.image.tostring(superficie, "RGBA", True)
    glWindowPos2d(x, y)
    glDrawPixels(superficie.get_width(), superficie.get_height(),
                 GL_RGBA, GL_UNSIGNED_BYTE, dados)


# ---------------------------------------------------------------- programa

def configurar_opengl(largura, altura):
    glViewport(0, 0, largura, altura)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    perspectiva(45, largura / altura, 0.1, 100.0)
    glMatrixMode(GL_MODELVIEW)

    glClearColor(0.94, 0.95, 0.96, 1.0)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glLightfv(GL_LIGHT0, GL_AMBIENT, (0.35, 0.35, 0.35, 1.0))
    glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.85, 0.85, 0.85, 1.0))
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glEnable(GL_NORMALIZE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


def main():
    parser = argparse.ArgumentParser(description="Visualizacao 3D da temperatura do ESP32")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--ip", help="IP do ESP32 (aparece no LCD e no Monitor Serial)")
    grupo.add_argument("--simular", action="store_true", help="usa temperatura simulada")
    parser.add_argument("--intervalo", type=float, default=2.0,
                        help="segundos entre leituras do ESP32 (padrao 2)")
    args = parser.parse_args()

    fonte_dados = FonteSimulada() if args.simular else FonteESP32(args.ip, args.intervalo)

    pygame.init()
    largura, altura = 1000, 650
    pygame.display.set_mode((largura, altura), pygame.DOUBLEBUF | pygame.OPENGL)
    pygame.display.set_caption("PI - Temperatura do ESP32 em 3D")
    configurar_opengl(largura, altura)

    fonte_grande = pygame.font.SysFont("arial", 30, bold=True)
    fonte = pygame.font.SysFont("arial", 19)
    relogio = pygame.time.Clock()

    fracao = 1.0
    cor = FAIXAS[1][1]
    angulo_camera = -32.0  # comeca de lado para ver o gelo e a frente do cooler
    angulo_pas = 0.0
    velocidade_pas = 0.0
    vento = Vento()

    rodando = True
    while rodando:
        dt = relogio.tick(60) / 1000.0
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                rodando = False
            elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
                rodando = False

        teclas = pygame.key.get_pressed()
        if teclas[pygame.K_LEFT]:
            angulo_camera -= 60 * dt
        if teclas[pygame.K_RIGHT]:
            angulo_camera += 60 * dt

        temperatura, cooler, erro = fonte_dados.leitura()

        # Atualiza o estado visual de forma suave
        if temperatura is not None:
            fracao = aproximar(fracao, fracao_de_gelo(temperatura), 1.5, dt)
            alvo_cor = cor_da_faixa(temperatura)
            cor = tuple(aproximar(c, a, 3.0, dt) for c, a in zip(cor, alvo_cor))
        velocidade_pas = aproximar(velocidade_pas, 720.0 if cooler else 0.0, 1.2, dt)
        angulo_pas = (angulo_pas + velocidade_pas * dt) % 360
        intensidade_vento = velocidade_pas / 720.0
        vento.atualizar(dt, intensidade_vento)

        # Cena 3D
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        rad = math.radians(angulo_camera)
        cx, cz = 1.2 + 7.5 * math.sin(rad), 7.5 * math.cos(rad)
        olhar_para((cx, 3.4, cz), (1.2, 0.7, 0.0))
        glLightfv(GL_LIGHT0, GL_POSITION, (3.0, 6.0, 5.0, 1.0))

        desenhar_piso()
        desenhar_cooler(angulo_pas, cooler)
        desenhar_poca(0.35 + 1.5 * (1.0 - fracao))
        vento.desenhar(intensidade_vento)
        desenhar_gelo(fracao, cor)

        # Painel de texto
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        if temperatura is not None:
            desenhar_texto(fonte_grande, 20, altura - 50, f"Temperatura: {temperatura:.1f} °C")
            desenhar_texto(fonte, 20, altura - 80, f"Faixa: {descricao_da_faixa(temperatura)}")
        else:
            desenhar_texto(fonte_grande, 20, altura - 50, "Temperatura: --")
        cor_status = (20, 90, 180) if cooler else (90, 90, 90)
        desenhar_texto(fonte, 20, altura - 108,
                       f"Cooler: {'LIGADO' if cooler else 'DESLIGADO'}", cor_status)
        desenhar_texto(fonte, 20, 20,
                       f"Fonte: {fonte_dados.descricao}   |   liga > {TEMP_LIGAR:.0f} °C, "
                       f"desliga < {TEMP_DESLIGAR:.0f} °C   |   setas giram a camera",
                       (80, 80, 80))
        if erro:
            desenhar_texto(fonte, 20, altura - 136, erro, (180, 40, 30))
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()

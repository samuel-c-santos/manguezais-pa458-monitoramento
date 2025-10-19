# -*- coding: utf-8 -*-
# QGIS 3.x — Aplica Singleband Pseudocolor (DISCRETE) na Banda 3 (NDVI)
# a todas as camadas raster do projeto, com 5 classes por Intervalo Igual.

from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProject, QgsMapLayerType, QgsRasterLayer, QgsRasterBandStats,
    QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer
)

# --- Configurações ---
BANDA_NDVI = 3  # usar a banda 3 de cada raster (1-based)
ROTULOS = [
    u"Não-Vegetação/Água",
    u"Estresse Severo/Degradação",
    u"Estresse Moderado/Baixa Biomassa",
    u"Saúde Razoável",
    u"Saudável e Vigoroso"
]

# Paleta Vermelho (baixo) -> Verde escuro (alto)
CORES = [
    QColor(215,  25,  28),  # vermelho
    QColor(253, 174,  97),  # laranja
    QColor(255, 255, 191),  # amarelo claro
    QColor(171, 221, 164),  # verde claro
    QColor("#1a9641")       # verde escuro (saudável e vigoroso)
]

def aplica_pseudocolor_ndvi_discreto(layer, banda=BANDA_NDVI):
    """Aplica simbologia Singleband Pseudocolor (DISCRETE) na banda NDVI indicada."""
    if not isinstance(layer, QgsRasterLayer):
        return

    prov = layer.dataProvider()
    if prov is None:
        raise RuntimeError(u"Sem dataProvider para a camada '{}'.".format(layer.name()))
    if prov.bandCount() < banda:
        raise RuntimeError(u"Camada '{}' tem apenas {} banda(s); precisa da banda {}."
                           .format(layer.name(), prov.bandCount(), banda))

    # Estatísticas min/max da banda (QGIS 3)
    stats = prov.bandStatistics(
        banda,
        QgsRasterBandStats.Min | QgsRasterBandStats.Max
    )
    vmin = stats.minimumValue
    vmax = stats.maximumValue

    if vmin is None or vmax is None:
        raise RuntimeError(u"Falha ao obter min/max da banda {} em '{}'.".format(banda, layer.name()))
    if vmin == vmax:
        vmin -= 0.001
        vmax += 0.001

    # Intervalo Igual para 5 classes
    n_classes = 5
    step = float(vmax - vmin) / float(n_classes)
    limites_superiores = [vmin + step * (i + 1) for i in range(n_classes)]

    # Itens de cor (cada item é o limite superior da classe no modo DISCRETE)
    itens = []
    for limite, rotulo, cor in zip(limites_superiores, ROTULOS, CORES):
        itens.append(QgsColorRampShader.ColorRampItem(limite, cor, rotulo))

    # Shader de cores DISCRETE
    colorRampShader = QgsColorRampShader()
    colorRampShader.setColorRampType(QgsColorRampShader.Discrete)
    colorRampShader.setColorRampItemList(itens)

    # RasterShader envolvendo o ColorRampShader
    rasterShader = QgsRasterShader()
    rasterShader.setRasterShaderFunction(colorRampShader)

    # Renderer Singleband Pseudocolor (QGIS 3)
    renderer = QgsSingleBandPseudoColorRenderer(prov, banda, rasterShader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()

def aplicar_em_todos_os_rasters(banda=BANDA_NDVI):
    camadas = QgsProject.instance().mapLayers().values()
    aplicadas = 0
    puladas = []

    for l in camadas:
        if l.type() != QgsMapLayerType.RasterLayer:
            continue
        try:
            aplica_pseudocolor_ndvi_discreto(l, banda=banda)
            aplicadas += 1
        except Exception as e:
            puladas.append((l.name(), str(e)))

    # Atualiza o canvas
    try:
        iface.mapCanvas().refresh()
    except:
        pass

    # Log no console
    print(u"[OK] Simbologia aplicada em {} camada(s) raster.".format(aplicadas))
    if puladas:
        print(u"[Aviso] Camadas puladas:")
        for nome, motivo in puladas:
            print(u"  - {} -> {}".format(nome, motivo))

# ---- Executar ----
aplicar_em_todos_os_rasters(banda=BANDA_NDVI)

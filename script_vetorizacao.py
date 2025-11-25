# -*- coding: utf-8 -*-
import os
import processing
from qgis.core import (
    QgsProject, QgsMapLayerType, QgsVectorLayer, QgsRasterBandStats,
    QgsSymbol, QgsRendererCategory, QgsCategorizedSymbolRenderer
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt

# --- CONFIGURAÇÕES ---
# Pasta onde os vetores resultantes (.gpkg) serão salvos
PASTA_SAIDA = r"G:\Meu Drive\PA458_ByPolygons\final\sem_urb"

# Definição das Classes (1 a 5)
ROTULOS = [
    u"Não-Vegetação/Água",
    u"Estresse Severo/Degradação",
    u"Estresse Moderado/Baixa Biomassa",
    u"Saúde Razoável",
    u"Saudável e Vigoroso"
]
CORES_HEX = ["#d7191c", "#fdae61", "#ffffbf", "#abdda4", "#1a9641"]

def definir_simbologia_vetor(layer_vetor):
    """Aplica a simbologia categorizada no campo 'DN'."""
    categorias = []
    for i, (rotulo, hex_cor) in enumerate(zip(ROTULOS, CORES_HEX)):
        valor_classe = i + 1
        
        simbolo = QgsSymbol.defaultSymbol(layer_vetor.geometryType())
        simbolo.setColor(QColor(hex_cor))
        simbolo.setOpacity(1)
        # Sem contorno para parecer raster
        simbolo.symbolLayer(0).setStrokeStyle(Qt.NoPen) 
        
        categoria = QgsRendererCategory(valor_classe, simbolo, rotulo)
        categorias.append(categoria)

    renderer = QgsCategorizedSymbolRenderer("DN", categorias)
    layer_vetor.setRenderer(renderer)
    layer_vetor.triggerRepaint()

def processar_camadas_carregadas():
    # 1. Validação da Pasta
    if not os.path.exists(PASTA_SAIDA):
        try:
            os.makedirs(PASTA_SAIDA)
        except Exception as e:
            print(u"Erro ao criar pasta: {}".format(e))
            return

    # 2. Obter todas as camadas RASTER carregadas no painel
    rasters_projeto = [l for l in QgsProject.instance().mapLayers().values() 
                       if l.type() == QgsMapLayerType.RasterLayer]
    
    print(u"--- Iniciando conversão de {} camadas carregadas ---".format(len(rasters_projeto)))

    root = QgsProject.instance().layerTreeRoot()

    for layer in rasters_projeto:
        print(u"\nProcessando: {}".format(layer.name()))

        # Lógica inteligente para definir a banda
        # Se for um recorte novo (geralmente vira banda 1), usa a 1.
        # Se for o original com várias bandas, tentamos a 3 (NDVI).
        prov = layer.dataProvider()
        banda_uso = 1 
        if prov.bandCount() >= 3:
            banda_uso = 3
            print(u"  > Detectado multicamada: Usando Banda 3")
        else:
            print(u"  > Detectado banda única: Usando Banda 1")

        # 3. Estatísticas Min/Max
        stats = prov.bandStatistics(banda_uso, QgsRasterBandStats.Min | QgsRasterBandStats.Max)
        vmin, vmax = stats.minimumValue, stats.maximumValue

        if vmin is None or vmax is None or vmin == vmax:
            print(u"  > PULO: Camada vazia ou constante.")
            continue

        # 4. Criar Tabela de Reclassificação (Intervalo Igual)
        n_classes = 5
        step = (vmax - vmin) / n_classes
        reclass_table = []
        for i in range(n_classes):
            limite_inf = vmin + (step * i)
            limite_sup = vmin + (step * (i + 1))
            if i == n_classes - 1: limite_sup += 0.0001
            reclass_table.extend([limite_inf, limite_sup, i + 1])

        try:
            # 5. Reclassificar (Memória)
            # Transforma valores quebrados em 1, 2, 3, 4, 5
            res_reclass = processing.run("native:reclassifybytable", {
                'INPUT_RASTER': layer,
                'RASTER_BAND': banda_uso,
                'TABLE': reclass_table,
                'NO_DATA': -9999,
                'RANGE_BOUNDARIES': 0, 
                'NODATA_FOR_MISSING': True,
                'DATA_TYPE': 5, # Int16
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            
            # 6. Poligonizar (Salvar em Disco)
            nome_seguro = layer.name().replace(" ", "_").replace("/", "-")
            caminho_final = os.path.join(PASTA_SAIDA, "{}_vetor.gpkg".format(nome_seguro))
            
            print(u"  > Gerando vetor em: {}".format(caminho_final))
            
            processing.run("gdal:polygonize", {
                'INPUT': res_reclass['OUTPUT'],
                'BAND': 1,
                'FIELD': 'DN',
                'EIGHT_CONNECTEDNESS': False,
                'OUTPUT': caminho_final
            })

            # 7. Carregar e Estilizar
            vetor_layer = QgsVectorLayer(caminho_final, layer.name(), "ogr")
            if vetor_layer.isValid():
                # Adiciona ao projeto sem desenhar ainda
                QgsProject.instance().addMapLayer(vetor_layer, False)
                
                # Tenta colocar o vetor logo acima do raster original na árvore
                node_raster = root.findLayer(layer.id())
                if node_raster:
                    parent = node_raster.parent()
                    idx = parent.children().index(node_raster)
                    parent.insertLayer(idx, vetor_layer) # Insere acima
                    # Opcional: Desligar o raster original
                    # node_raster.setItemVisibilityChecked(False)
                else:
                    root.addLayer(vetor_layer)

                definir_simbologia_vetor(vetor_layer)
                print(u"  > Sucesso.")
            else:
                print(u"  > Erro ao carregar o arquivo gerado.")

        except Exception as e:
            print(u"  > Falha: {}".format(e))

    print(u"\n--- Processamento finalizado! ---")

# Executar
processar_camadas_carregadas()
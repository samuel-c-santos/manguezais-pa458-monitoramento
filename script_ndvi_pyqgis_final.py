# -*- coding: utf-8 -*-
import os
import processing
from qgis.core import (
    QgsProject, QgsMapLayerType, QgsRasterLayer, QgsRasterBandStats,
    QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer,
    QgsProcessingException
)
from qgis.utils import iface

# --- Configurações ---
CAMADA_MASCARA = "buffer_total"
PASTA_SAIDA = r"G:\Meu Drive\PA458_ByPolygons\final\sem_urb"
BANDA_NDVI = 3  # Mantendo a lógica do seu script anterior

# --- (Reutilizando sua função de simbologia para consistência) ---
def aplica_pseudocolor_ndvi_discreto(layer, banda=BANDA_NDVI):
    rotulos = [
        u"Não-Vegetação/Água", u"Estresse Severo/Degradação",
        u"Estresse Moderado/Baixa Biomassa", u"Saúde Razoável", u"Saudável e Vigoroso"
    ]
    cores_hex = ["#d7191c", "#fdae61", "#ffffbf", "#abdda4", "#1a9641"]
    
    prov = layer.dataProvider()
    stats = prov.bandStatistics(banda, QgsRasterBandStats.Min | QgsRasterBandStats.Max)
    vmin, vmax = stats.minimumValue, stats.maximumValue
    
    if vmin is None or vmax is None or vmin == vmax:
        return # Evita erro em rasters vazios
        
    n_classes = 5
    step = (vmax - vmin) / n_classes
    itens = []
    
    for i, (rotulo, hex_cor) in enumerate(zip(rotulos, cores_hex)):
        val_limite = vmin + step * (i + 1)
        itens.append(QgsColorRampShader.ColorRampItem(val_limite, QColor(hex_cor), rotulo))

    colorRampShader = QgsColorRampShader()
    colorRampShader.setColorRampType(QgsColorRampShader.Discrete)
    colorRampShader.setColorRampItemList(itens)
    rasterShader = QgsRasterShader()
    rasterShader.setRasterShaderFunction(colorRampShader)
    
    renderer = QgsSingleBandPseudoColorRenderer(prov, banda, rasterShader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()

# --- Função Principal de Processamento ---
def processar_recorte_e_estilo():
    # 1. Verificar diretório
    if not os.path.exists(PASTA_SAIDA):
        try:
            os.makedirs(PASTA_SAIDA)
        except OSError:
            print(u"Erro: Não foi possível criar a pasta {}".format(PASTA_SAIDA))
            return

    # 2. Obter a camada de máscara
    mascara_layers = QgsProject.instance().mapLayersByName(CAMADA_MASCARA)
    if not mascara_layers:
        print(u"Erro: Camada máscara '{}' não encontrada.".format(CAMADA_MASCARA))
        return
    mascara = mascara_layers[0]

    # 3. Listar rasters (evitando processar a própria máscara se ela fosse raster, ou os outputs já gerados)
    root = QgsProject.instance().layerTreeRoot()
    # Pegamos a lista de IDs para iterar com segurança
    layer_ids = [l.id() for l in QgsProject.instance().mapLayers().values()]

    processados = 0

    for layer_id in layer_ids:
        layer = QgsProject.instance().mapLayer(layer_id)
        
        # Filtros: Deve ser Raster e não deve ser um arquivo já salvo na pasta de saída (para evitar loop)
        if layer.type() != QgsMapLayerType.RasterLayer:
            continue
        if layer.source().startswith(PASTA_SAIDA):
            continue
            
        print(u"Processando: {}".format(layer.name()))
        
        # Caminho de saída
        nome_saida = "{}.tif".format(layer.name()) # Garante extensão .tif
        caminho_saida = os.path.join(PASTA_SAIDA, nome_saida)

        # 4. Executar GDAL Clip by Mask
        try:
            params = {
                'INPUT': layer,
                'MASK': mascara,
                'SOURCE_CRS': layer.crs(),
                'TARGET_CRS': layer.crs(),
                'KEEP_RESOLUTION': True,
                'NODATA': -9999, # Define valor nulo para a área fora da máscara
                'ALPHA_BAND': False,
                'OPTIONS': '',
                'DATA_TYPE': 0, # Use Input Layer Data Type
                'OUTPUT': caminho_saida
            }
            
            processing.run("gdal:cliprasterbymasklayer", params)

            # 5. Carregar o novo arquivo
            novo_layer = QgsRasterLayer(caminho_saida, layer.name()) # Mantém mesmo nome
            
            if not novo_layer.isValid():
                print(u"Falha ao carregar: {}".format(caminho_saida))
                continue

            # 6. Adicionar ao projeto e posicionar na árvore
            # Adiciona sem colocar na árvore automaticamente primeiro
            QgsProject.instance().addMapLayer(novo_layer, False)
            
            # Encontra o nó da camada original na árvore
            node_original = root.findLayer(layer.id())
            
            if node_original:
                # Insere o novo nó no mesmo pai, logo antes (acima) do original
                parent = node_original.parent()
                index = parent.children().index(node_original)
                parent.insertLayer(index, novo_layer)
                
                # Opcional: Desligar a visualização da camada antiga para não confundir
                # root.findLayer(layer.id()).setItemVisibilityChecked(False)
            else:
                root.addLayer(novo_layer)

            # 7. Aplicar Simbologia
            aplica_pseudocolor_ndvi_discreto(novo_layer, banda=BANDA_NDVI)
            processados += 1

        except Exception as e:
            print(u"Erro ao processar {}: {}".format(layer.name(), e))

    print(u"--- Concluído! {} camadas recortadas e estilizadas em: {} ---".format(processados, PASTA_SAIDA))

# Executar
processar_recorte_e_estilo()
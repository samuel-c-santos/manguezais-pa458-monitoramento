# -*- coding: utf-8 -*-
import processing
import os
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsMapLayerType, 
    QgsSymbol, QgsRendererCategory, QgsCategorizedSymbolRenderer
)
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtGui import QColor

# --- CONFIGURAÇÕES ---
# Lista de camadas para IGNORAR (não processar)
CAMADAS_IGNORAR = [
    "Buffer Oeste", "PA458_Leste_12km", "PA-458_12km",
    "PA-458", "Buffer Leste", "mapbiomas_bragança", "PA458_Oeste_12km"
]

# Configuração da Simbologia (Igual à original)
ROTULOS_MAPA = {
    1: u"Não-Vegetação/Água",
    2: u"Estresse Severo/Degradação",
    3: u"Estresse Moderado/Baixa Biomassa",
    4: u"Saúde Razoável",
    5: u"Saudável e Vigoroso"
}
CORES_HEX = ["#d7191c", "#fdae61", "#ffffbf", "#abdda4", "#1a9641"]

def aplicar_simbologia(layer_vetor):
    """Reaplica a simbologia classificada no arquivo dissolvido."""
    categorias = []
    for i, hex_cor in enumerate(CORES_HEX):
        valor_classe = i + 1
        rotulo = ROTULOS_MAPA.get(valor_classe, "Outros")
        
        simbolo = QgsSymbol.defaultSymbol(layer_vetor.geometryType())
        simbolo.setColor(QColor(hex_cor))
        simbolo.setOpacity(1)
        simbolo.symbolLayer(0).setStrokeStyle(Qt.NoPen) # Sem borda
        
        categoria = QgsRendererCategory(valor_classe, simbolo, rotulo)
        categorias.append(categoria)

    renderer = QgsCategorizedSymbolRenderer("DN", categorias)
    layer_vetor.setRenderer(renderer)
    layer_vetor.triggerRepaint()

def dissolver_calcular_posicionar():
    root = QgsProject.instance().layerTreeRoot()
    # Pega lista de camadas (cópia da lista atual para evitar erros ao modificar a árvore)
    camadas_iniciais = [l for l in QgsProject.instance().mapLayers().values()]
    
    print(u"--- INICIANDO PROCESSAMENTO: DISSOLVE + ÁREA + ESTILO ---")

    for layer in camadas_iniciais:
        # Filtros de Segurança
        if layer.type() != QgsMapLayerType.VectorLayer: continue
        if layer.name() in CAMADAS_IGNORAR: continue
        if "_dissolvido" in layer.name(): continue # Evita reprocessar o resultado

        print(u"\nProcessando: {}".format(layer.name()))

        # 1. Definir caminho de saída
        caminho_origem = layer.source().split("|")[0]
        pasta = os.path.dirname(caminho_origem)
        nome_novo = "{}_dissolvido.gpkg".format(layer.name())
        caminho_saida = os.path.join(pasta, nome_novo)

        # 2. Executar DISSOLVE (Agrupa geometrias pelo DN)
        try:
            processing.run("native:dissolve", {
                'INPUT': layer,
                'FIELD': ['DN'],
                'OUTPUT': caminho_saida
            })
            
            # 3. Carregar a camada (SEM adicionar na árvore ainda)
            vlayer = QgsVectorLayer(caminho_saida, layer.name() + "_FINAL", "ogr")
            if not vlayer.isValid():
                print(u"Erro ao carregar camada gerada.")
                continue

            # 4. Adicionar Campos e Calcular Área (Equivalente à Calculadora de Campo)
            # Iniciamos edição para alterar a tabela
            vlayer.startEditing()
            
            # Adiciona colunas
            pr = vlayer.dataProvider()
            pr.addAttributes([
                QgsField("Rotulo", QVariant.String, len=100),
                QgsField("Area_Ha", QVariant.Double) # Campo Decimal
            ])
            vlayer.updateFields()

            # Itera sobre as 5 feições para preencher
            for feat in vlayer.getFeatures():
                dn = feat['DN']
                
                # A. Preencher Rótulo
                feat['Rotulo'] = ROTULOS_MAPA.get(dn, "Indefinido")
                
                # B. Calcular Área ($area / 10000)
                # geom.area() retorna em metros quadrados (se projeção for UTM/métrica)
                area_hectares = feat.geometry().area() / 10000.0
                feat['Area_Ha'] = round(area_hectares, 4)
                
                vlayer.updateFeature(feat)
            
            vlayer.commitChanges()

            # 5. Adicionar ao Projeto e POSICIONAR NA ÁRVORE
            QgsProject.instance().addMapLayer(vlayer, False) # False = não põe na árvore auto
            
            # Encontra onde está a camada original
            node_original = root.findLayer(layer.id())
            if node_original:
                parent_group = node_original.parent()
                # Pega o índice (posição) da original
                idx = parent_group.children().index(node_original)
                # Insere a nova camada EXATAMENTE nesse índice (empurra a original para baixo)
                parent_group.insertLayer(idx, vlayer)
                
                # Opcional: Expandir a nova e colapsar a velha
                node_novo = root.findLayer(vlayer.id())
                node_novo.setExpanded(True)
                node_original.setExpanded(False)
            else:
                root.addLayer(vlayer) # Fallback se não achar

            # 6. Aplicar Simbologia
            aplicar_simbologia(vlayer)
            
            print(u"  > Sucesso! Salvo, calculado e posicionado acima da original.")

        except Exception as e:
            print(u"Erro crítico em {}: {}".format(layer.name(), e))

    print(u"\n--- FIM ---")

dissolver_calcular_posicionar()
# -*- coding: utf-8 -*-
import processing
import os
import csv
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsMapLayerType, QgsVectorFileWriter
)

# --- CONFIGURAÇÕES ---
# Pasta Principal
PASTA_BASE = r"H:\Meu Drive\UFRA\PRÉ PROJETO DE TCC\PRODUTOS TCC\tabelas_sankey"

# Configurações de Filtro
IGNORAR = ["Buffer", "mapbiomas", "dissolvido", "sankey", "transicao"]

def renomear_campo_dn(layer, ano):
    """Renomeia 'DN' para 'CLASSE_20xx'."""
    novo_nome = "Class{}".format(ano)
    
    fields_mapping = []
    for field in layer.fields():
        if field.name() == 'DN':
            fields_mapping.append({
                'expression': '"DN"', 
                'length': field.length(), 
                'name': novo_nome, 
                'precision': field.precision(), 
                'type': field.type()
            })
            
    res = processing.run("native:refactorfields", {
        'INPUT': layer,
        'FIELDS_MAPPING': fields_mapping,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })
    return res['OUTPUT']

def exportar_produtos_finais(layer_final, nome_base):
    """Salva o CSV (para o gráfico) e o SHP (para auditoria)."""
    
    # 1. Salvar SHAPEFILE (Auditoria)
    caminho_shp = os.path.join(PASTA_BASE, "{}.shp".format(nome_base))
    
    print(u"  > Salvando Shapefile para auditoria...")
    processing.run("native:savefeatures", {
        'INPUT': layer_final,
        'OUTPUT': caminho_shp
    })
    print(u"    [OK] Shapefile salvo em: {}".format(caminho_shp))
    
    # Carrega o SHP no projeto para você ver na hora
    vlayer = QgsVectorLayer(caminho_shp, nome_base, "ogr")
    if vlayer.isValid():
        QgsProject.instance().addMapLayer(vlayer)

    # 2. Salvar CSV (Para o R)
    caminho_csv = os.path.join(PASTA_BASE, "{}.csv".format(nome_base))
    
    campos_classe = [f.name() for f in layer_final.fields() if f.name().startswith("CLASSE_")]
    campos_classe.sort() 
    
    dados_agrupados = {}
    
    for feat in layer_final.getFeatures():
        # Tupla de histórico (5, 5, 4...)
        historico = tuple(feat[c] for c in campos_classe)
        area_ha = feat.geometry().area() / 10000.0
        
        if historico in dados_agrupados:
            dados_agrupados[historico] += area_ha
        else:
            dados_agrupados[historico] = area_ha
            
    with open(caminho_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(campos_classe + ['area_ha'])
        for historico, area in dados_agrupados.items():
            writer.writerow(list(historico) + [round(area, 4)])
            
    print(u"    [OK] CSV salvo em: {}".format(caminho_csv))

def processar_tudo_com_auditoria():
    if not os.path.exists(PASTA_BASE):
        os.makedirs(PASTA_BASE)

    dados_mapa = {'Leste': {}, 'Oeste': {}}
    camadas = QgsProject.instance().mapLayers().values()
    
    print(u"--- 1. Identificando Camadas '_FINAL' ---")
    
    count = 0
    for l in camadas:
        if l.type() != QgsMapLayerType.VectorLayer: continue
        nome = l.name()
        
        # Filtro Rigoroso
        if not nome.upper().endswith("FINAL"): continue
        if any(ig in nome for ig in IGNORAR): continue

        partes = nome.split('_')
        lado = "Leste" if "Leste" in partes else "Oeste" if "Oeste" in partes else None
        
        ano = None
        for p in partes:
            if p.isdigit() and len(p) == 4:
                ano = int(p)
                break
        
        if lado and ano:
            dados_mapa[lado][ano] = l
            print(u"  Capturado: {} | {}".format(lado, ano))
            count += 1
            
    if count == 0:
        print(u"ERRO: Nenhuma camada '_FINAL' encontrada.")
        return

    # --- 2. Loop de Intersecção ---
    for lado in ['Leste', 'Oeste']:
        anos = sorted(dados_mapa[lado].keys())
        if not anos: continue
            
        print(u"\n--- Processando Setor: {} ---".format(lado))
        
        ano_base = anos[0]
        layer_acumulado = renomear_campo_dn(dados_mapa[lado][ano_base], ano_base)
        
        for ano_prox in anos[1:]:
            print(u"  > Cruzando {} com {}...".format(ano_base, ano_prox))
            layer_prox = renomear_campo_dn(dados_mapa[lado][ano_prox], ano_prox)
            
            res = processing.run("native:intersection", {
                'INPUT': layer_acumulado,
                'OVERLAY': layer_prox,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            layer_acumulado = res['OUTPUT']
            ano_base = ano_prox 
            
        # Exporta SHP e CSV
        nome_base = "transicao_completa_{}".format(lado)
        exportar_produtos_finais(layer_acumulado, nome_base)

    print(u"\n--- Concluído! Verifique a pasta e o painel de camadas. ---")

processar_tudo_com_auditoria()
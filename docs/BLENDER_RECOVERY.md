# Projetos 3D recuperados para o Blender

Este pacote contém três cenas **editáveis no Blender 4.x**, reconstruídas a partir dos arquivos GLB já publicados no portfólio.

| Cena | Malhas | Triângulos | Materiais |
|---|---:|---:|---:|
| Creekside Cottage & Watchtower | 28 | 15.582 | 14 |
| Coastal Fishing Hut & Pier | 49 | 13.718 | 27 |
| Rural Railway Stop & Freight Wagon | 64 | 21.722 | 37 |

## Como abrir

1. Extraia todos os arquivos do ZIP.
2. Abra o Blender 4.x.
3. Use **File > Open** e selecione o arquivo `.blend` desejado.
4. No Outliner, selecione as malhas para inspecionar e editar sua geometria e materiais.

Os modelos são importados pelo Blender a partir dos GLBs exportados. A conversão de eixos do formato glTF para o espaço do Blender é feita pelo importador oficial.

## O que foi preservado

- Objetos de malha e seus vértices, faces e transformações importáveis.
- Materiais e propriedades compatíveis com o formato GLB.
- Organização em objetos editáveis, com as contagens verificadas no relatório `import_report.json`.

## O que **não** foi recuperado

Estes **não são os arquivos de autoria originais**. Um GLB não preserva o histórico de edição, os modificadores que já foram aplicados, scripts de geração, configurações de renderização não exportadas nem outros dados que não estejam no GLB. Algumas configurações de materiais podem exigir ajustes manuais conforme a versão do Blender.

## Proveniência e verificação

O relatório `import_report.json` registra o nome de cada GLB de origem, seu SHA-256, a versão do Blender e as contagens da geometria importada. As três cenas foram geradas e validadas em uma execução automatizada do GitHub Actions.

Para repetir a recuperação a partir do repositório, execute:

```bash
blender --background --factory-startup --python-exit-code 1 --python tools/recover_blender_projects.py -- --output-dir blender
```

A importação cria uma nova base editável. Melhorias futuras feitas diretamente nos `.blend` precisam ser salvas e versionadas separadamente.

## Revisão visual automatizada

O pacote também contém a pasta `qa/`, com nove imagens renderizadas diretamente no Blender (três ângulos por projeto), além de `qa_report.json` com limites espaciais e hashes das imagens. Essas capturas permitem verificar o enquadramento e a legibilidade da geometria importada. São **renders neutros de inspeção**, não os renders finais de autoria nem uma certificação automática de qualidade artística.

# Play Musica – ISO bootável (jukebox de bar)

Ao ligar o computador pelo pendrive, o sistema sobe **direto no Jukebox em tela cheia**
(sem desktop, sem barra de navegador, parecido com o Batocera).

## Como gerar a ISO no GitHub
1. Crie um repositório no GitHub e envie **todo o conteúdo desta pasta**.
2. Abra a aba **Actions → Gerar ISO Play Musica → Run workflow** (também roda sozinho a cada envio).
3. Espere uns 15–25 minutos. No fim, baixe **PlayMusica-ISO** em *Artifacts* (é um .zip com o `PlayMusica.iso`).

## Como gravar no pendrive
Use o **Rufus** (modo **DD Image** quando perguntar) ou o **balenaEtcher**.
Esse pendrive vira só o "sistema". Dá boot em BIOS e UEFI.

## Como colocar as músicas
- **Recomendado:** em outro pendrive ou HD, crie a pasta `músicas` (com as pastas dos artistas dentro) e,
  se quiser, a pasta `imagem` com as capas. Plugue antes de ligar (ou depois) – o jukebox detecta sozinho
  e abre a lista em ⚙ Configurações → 📚 Bibliotecas.
  Se houver só uma fonte com músicas ao ligar, ele já carrega sozinho.
- Também dá para pôr músicas em `jukebox/musicas` **antes** de gerar a ISO (a ISO fica maior;
  o GitHub não aceita arquivo acima de 100 MB, e é lento com muitos GB).
- Som de moeda: coloque `jukebox/som/credito.mp3` (sem ele o sistema usa um bipe padrão).

## Observações
- Configurações (crédito, preço) não ficam salvas após desligar, pois a ISO roda "limpa" a cada boot.
- Para uso no Windows continue usando `jukebox/INICIAR.bat`.

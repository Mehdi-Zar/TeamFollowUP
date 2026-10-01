# Autorites racines pour le build Docker

Sur un reseau qui inspecte le HTTPS (Zscaler Internet Access, proxy d'entreprise),
`npm install` et `pip install` echouent pendant `docker compose build` avec
`unable to get local issuer certificate` : le conteneur ne connait pas l'autorite
racine du proxy, que le poste Windows, lui, connait.

Deposer ici le certificat racine du proxy, au format PEM, avec l'extension `.crt`.
Le Dockerfile l'ajoute aux autorites de confiance de npm et de pip pendant le build.
La verification des certificats reste active.

Les fichiers `.crt` de ce dossier ne sont pas versionnes (`.gitignore`) : ils sont
propres a un poste. Dossier vide (CI, production) : le build ne fait confiance
qu'aux autorites publiques, comme avant.

Exporter le certificat Zscaler depuis le magasin Windows (PowerShell) :

```powershell
$c = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Subject -match 'Zscaler Root CA' } | Select-Object -First 1
$pem = "-----BEGIN CERTIFICATE-----`n" + [Convert]::ToBase64String($c.RawData, 'InsertLineBreaks') + "`n-----END CERTIFICATE-----`n"
[IO.File]::WriteAllText("$PWD\build-certs\zscaler-root-ca.crt", $pem)
```

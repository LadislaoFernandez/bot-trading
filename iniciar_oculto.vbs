' Arranca la aplicacion del bot oculta, en el icono junto a la hora (lo usa el inicio automatico de Windows)
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = carpeta
pyw = carpeta & "\python\pythonw.exe"
If fso.FileExists(pyw) Then
    ' instalacion con el instalador: usa directamente el Python que viene con la app
    sh.Run """" & pyw & """ """ & carpeta & "\app.py"" --minimizado", 0, False
Else
    sh.Run """" & carpeta & "\iniciar_bot.bat"" --minimizado", 0, False
End If

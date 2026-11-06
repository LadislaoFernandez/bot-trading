' Arranca la aplicacion del bot oculta, en el icono junto a la hora (lo usa el inicio automatico de Windows)
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = carpeta
sh.Run """" & carpeta & "\iniciar_bot.bat"" --minimizado", 0, False

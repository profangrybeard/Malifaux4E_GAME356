Get-ChildItem -Path . -Filter *.pdf -Recurse | ForEach-Object {
>>     $pdfFile = $_.FullName
>>     $pngFile = ($pdfFile -replace "\.pdf$", "") + ".png"
>>     gswin64c -dSAFER -dBATCH -dNOPAUSE -dQUIET -sDEVICE=png16m -r150 -dFirstPage=1 -dLastPage=1 -sOutputFile="$pngFile" "$pdfFile"
>> }
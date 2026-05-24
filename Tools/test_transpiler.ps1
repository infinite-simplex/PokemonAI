$ErrorActionPreference = "Stop"
   $INPUT    = "test_transpiler1.c"
   $EXPECTED = "test_transpiler1_expect.c"
   $OUTPUT   = "test_transpiler1_out.c"

   Copy-Item $INPUT $OUTPUT
   python3 agbcc_transpiler.py $OUTPUT

   $diff = diff (Get-Content $EXPECTED) (Get-Content $OUTPUT)
   if ($diff) {
       Write-Host "FAIL"
       Write-Host ($diff | Out-String)
       exit 1
   } else {
       Write-Host "PASS"
   }
   rm $OUTPUT
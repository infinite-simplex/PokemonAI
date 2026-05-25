$ErrorActionPreference = "Stop"
   $INPUT_FILENAME    = "test_transpiler1.c"
   $EXPECTED_FILENAME = "test_transpiler1_expect.c"
   $OUTPUT_FILENAME = "test_transpiler1_out.c"

   Copy-Item $INPUT_FILENAME $OUTPUT_FILENAME
   python3 agbcc_transpiler.py $OUTPUT_FILENAME

   $expected = Get-Content $EXPECTED_FILENAME
	$output   = Get-Content $OUTPUT_FILENAME

	if ($expected.Length -ne $output.Length) {
		Write-Host "FAIL (line count differs: expected $($expected.Length), got $($output.Length))"
		exit 1
	}

	$failed = $false
	for ($k = 0; $k -lt $expected.Length; $k++) {
		if ($expected[$k] -cne $output[$k]) {   # -cne = case-sensitive, exact match
			Write-Host "FAIL at line $($k + 1):"
			Write-Host "  expected: '$($expected[$k])'"
			Write-Host "  actual:   '$($output[$k])'"
			$failed = $true
		}
	}

	if ($failed) { 
		exit 1
	} else { 
		Write-Host "PASS"
		Remove-Item $OUTPUT_FILENAME
	}
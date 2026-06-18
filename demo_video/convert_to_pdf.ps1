param(
  [Parameter(Mandatory=$true)][string]$Docx,
  [Parameter(Mandatory=$true)][string]$Xlsx,
  [Parameter(Mandatory=$true)][string]$ReportPdf,
  [Parameter(Mandatory=$true)][string]$TrackerPdf
)
$ErrorActionPreference = "Stop"

# ---- Word: .docx -> PDF ----
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
  $doc = $word.Documents.Open($Docx, [ref]$false, [ref]$true)
  $doc.ExportAsFixedFormat($ReportPdf, 17)  # 17 = wdExportFormatPDF
  $doc.Close([ref]$false)
  Write-Output "report pdf OK: $ReportPdf"
} finally {
  $word.Quit()
  [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}

# ---- Excel: .xlsx -> PDF (fit to one page wide, landscape) ----
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
  $wb = $excel.Workbooks.Open($Xlsx)
  foreach ($ws in $wb.Worksheets) {
    $used = $ws.UsedRange
    # Wrap text so long content is fully shown (no clipping), top-aligned, then
    # grow row heights to fit the wrapped lines.
    $used.WrapText = $true
    $used.VerticalAlignment = -4160      # xlTop
    # Keep the title row un-wrapped so it overflows horizontally (readable) instead
    # of stacking into a narrow column A.
    $ws.Rows("1:1").WrapText = $false
    [void]$used.EntireRow.AutoFit()

    $ps = $ws.PageSetup
    $ps.Orientation = 2          # xlLandscape
    $ps.Zoom = $false
    $ps.FitToPagesWide = 1       # all columns on one page width...
    $ps.FitToPagesTall = $false  # ...but allow as many pages tall as needed
    $ps.LeftMargin = $excel.InchesToPoints(0.3)
    $ps.RightMargin = $excel.InchesToPoints(0.3)
    $ps.TopMargin = $excel.InchesToPoints(0.3)
    $ps.BottomMargin = $excel.InchesToPoints(0.3)
  }
  $wb.ExportAsFixedFormat(0, $TrackerPdf)  # 0 = xlTypePDF
  $wb.Close($false)
  Write-Output "tracker pdf OK: $TrackerPdf"
} finally {
  $excel.Quit()
  [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
}

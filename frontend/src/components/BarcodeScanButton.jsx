import { useEffect, useRef, useState } from 'react'
import { ScanBarcode, X } from 'lucide-react'

// MPN fast path (MotoLister gap #2): camera barcode scan where the browser
// supports BarcodeDetector (Chrome/Android — i.e. the shop-floor devices).
// USB keyboard-wedge scanners need nothing: they already type into inputs.
export default function BarcodeScanButton({ onScan }) {
  const [supported] = useState(() => 'BarcodeDetector' in window)
  const [open, setOpen] = useState(false)
  const videoRef = useRef(null)
  const stopRef = useRef(null)

  useEffect(() => {
    if (!open) return
    let alive = true
    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
        })
        if (!alive) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        stopRef.current = () => stream.getTracks().forEach((t) => t.stop())
        videoRef.current.srcObject = stream
        await videoRef.current.play()
        const detector = new window.BarcodeDetector()
        const tick = async () => {
          if (!alive) return
          try {
            const codes = await detector.detect(videoRef.current)
            if (codes.length) {
              onScan(codes[0].rawValue)
              setOpen(false)
              return
            }
          } catch { /* frame not ready */ }
          requestAnimationFrame(tick)
        }
        tick()
      } catch {
        setOpen(false)
      }
    }
    start()
    return () => {
      alive = false
      stopRef.current?.()
      stopRef.current = null
    }
  }, [open, onScan])

  if (!supported) return null
  return (
    <>
      <button className="btn-secondary btn-sm" type="button" onClick={() => setOpen(true)}>
        <ScanBarcode size={14} /> Scan
      </button>
      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal scan-modal" onClick={(e) => e.stopPropagation()}>
            <div className="section-head">
              <h3>Scan barcode</h3>
              <button className="btn-icon btn-sm" onClick={() => setOpen(false)} aria-label="Close">
                <X size={15} />
              </button>
            </div>
            <video ref={videoRef} className="scan-video" muted playsInline />
            <p className="muted small center">Point at the OEM barcode or part-number label.</p>
          </div>
        </div>
      )}
    </>
  )
}

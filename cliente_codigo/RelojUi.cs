using System;
using System.Windows.Forms;

namespace Transcripcion
{
    // Reloj que llama a la ventana cada tanto aunque esté escondida (arranque con Windows).
    class RelojUi
    {
        readonly Control dueno;
        readonly int ms;
        System.Threading.Timer t;
        public event EventHandler Tick;
        public RelojUi(Control c, int milisegundos) { dueno = c; ms = milisegundos; }
        public void Start()
        {
            if (t != null) return;
            t = new System.Threading.Timer(_ =>
            {
                try
                {
                    if (dueno.IsHandleCreated && !dueno.IsDisposed)
                        dueno.BeginInvoke(new Action(() => { var h = Tick; if (h != null && t != null) h(this, EventArgs.Empty); }));
                }
                catch { }
            }, null, ms, ms);
        }
        public void Stop() { if (t != null) { t.Dispose(); t = null; } }
    }
}

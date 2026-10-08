import json, numpy as np, soundfile as sf, torch, torch.nn as nn

x, sr = sf.read("input.wav", dtype="float32")
y, sr2 = sf.read("output.wav", dtype="float32")
if y.ndim > 1: y = y[:, 0]
L = len(x)
print("sr:", sr, sr2, "| długość input:", L, "output:", len(y), "| bloków w output:", len(y) / L)

class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(2, 64, batch_first=True)
        self.fc = nn.Linear(64, 1)
    def forward(self, x):
        h, _ = self.lstm(x)
        return self.fc(h)

sd = {k: torch.tensor(v, dtype=torch.float32)
      for k, v in json.load(open("sansamp_weights_pytorch_backup.json")).items()}
net = Net(); net.load_state_dict(sd); net.eval()

def esr(a, b): return float(np.sum((a - b) ** 2) / np.sum(a ** 2))

skip = sr  # pomiń pierwszą sekundę każdego bloku
for i in range(11):
    t = y[i * L:(i + 1) * L]
    if len(t) < L: print("brak bloku", i); break
    d = i / 10
    inp = torch.tensor(np.stack([x, np.full_like(x, d)], -1))[None]
    with torch.no_grad():
        p = net(inp)[0, :, 0].numpy()
    g = float(np.dot(t[skip:], p[skip:]) / np.dot(p[skip:], p[skip:]))
    print(f"drive {d:.1f}: ESR {esr(t[skip:], p[skip:]):.4f}, gain {g:.3f}")
import torch
import torch.nn as nn
import torchaudio
import argparse

device = torch.device("cpu")

class ParametricAmpModel(nn.Module):
    def __init__(self, hidden_size=64):
        super().__init__()
        self.lstm = nn.LSTM(input_size=2, hidden_size=hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x, state=None):
        out, state = self.lstm(x, state)
        out = self.fc(out)
        return out, state

def process_audio(input_file, output_file, drive_value, model_path="sansamp_model.pth"):
    model = ParametricAmpModel(hidden_size=64).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    audio, sr = torchaudio.load(input_file)
    audio = audio[0:1, :]
    total_samples = audio.shape[1]

    drive_tensor = torch.full((1, total_samples), drive_value)

    x_audio = audio.unsqueeze(-1).to(device)
    x_param = drive_tensor.unsqueeze(-1).to(device)
    x_full = torch.cat([x_audio, x_param], dim=2)

    block_size = 4096
    output_audio = torch.zeros(1, total_samples, 1).to(device)
    
    state = None

    with torch.no_grad():
        for start in range(0, total_samples, block_size):
            end = min(start + block_size, total_samples)
            x_block = x_full[:, start:end, :]
            
            out_block, state = model(x_block, state)
            output_audio[:, start:end, :] = out_block

    output = output_audio.squeeze(-1)
    torchaudio.save(output_file, output, sr)
    print(f"Zapisano plik: {output_file} z Drive = {drive_value}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Testowanie modelu na dowolnym pliku audio.")
    parser.add_argument("-i", "--input", type=str, default="test_riff.wav", help="Plik wejściowy (np. test_bass.wav)")
    parser.add_argument("-o", "--output", type=str, default="predicted.wav", help="Plik wyjściowy (np. predicted_bass.wav)")
    parser.add_argument("-d", "--drive", type=float, default=0.7, help="Wartość przesteru Drive (0.0 - 1.0)")
    
    args = parser.parse_args()
    
    process_audio(args.input, args.output, drive_value=args.drive)
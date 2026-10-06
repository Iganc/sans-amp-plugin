import torch
import torch.nn as nn
import torchaudio
import pandas as pd
from torch.utils.data import Dataset, DataLoader

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
BLOCK_SIZE = 4096

class SansAmpDataset(Dataset):
    def __init__(self, input_path, output_path, csv_path, block_size):
        in_wav, self.sr = torchaudio.load(input_path)
        out_wav, _ = torchaudio.load(output_path)
        
        in_wav = in_wav[0]
        out_wav = out_wav[0]
        in_wav = in_wav.repeat(11)
        
        min_len = min(in_wav.shape[0], out_wav.shape[0])
        self.in_wav = in_wav[:min_len]
        self.out_wav = out_wav[:min_len]
        
        df = pd.read_csv(csv_path)
        self.drive_params = torch.zeros(min_len)
        
        for i in range(len(df) - 1):
            start_sample = int(df.iloc[i]['time'] * self.sr)
            end_sample = int(df.iloc[i+1]['time'] * self.sr)
            val = df.iloc[i]['drive_value']
            
            end_sample = min(end_sample, min_len)
            self.drive_params[start_sample:end_sample] = float(val)
            
        last_start = int(df.iloc[-1]['time'] * self.sr)
        if last_start < min_len:
            self.drive_params[last_start:] = float(df.iloc[-1]['drive_value'])
            
        self.block_size = block_size
        self.num_blocks = min_len // block_size

    def __len__(self):
        return self.num_blocks

    def __getitem__(self, idx):
        start = idx * self.block_size
        end = start + self.block_size
        
        x_audio = self.in_wav[start:end].unsqueeze(1)
        x_param = self.drive_params[start:end].unsqueeze(1)
        x = torch.cat([x_audio, x_param], dim=1)
        
        y = self.out_wav[start:end].unsqueeze(1)
        return x, y

class ParametricAmpModel(nn.Module):
    def __init__(self, hidden_size=64):
        super().__init__()
        self.lstm = nn.LSTM(input_size=2, hidden_size=hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.fc(out)
        return out

def train():
    print(f"Rozpoczecie treningu PRO na akceleratorze: {device}")
    
    dataset = SansAmpDataset("input.wav", "output.wav", "drive_param.csv", BLOCK_SIZE)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True)
    
    model = ParametricAmpModel(hidden_size=64).to(device)
    criterion = nn.MSELoss()
    
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=10)
    
    epochs = 350
    best_loss = float('inf')
    
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        
        for batch_idx, (x, y) in enumerate(dataloader):
            x, y = x.to(device), y.to(device)
            
            optimizer.zero_grad()
            predictions = model(x)
            loss = criterion(predictions, y)
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item()
            
        avg_loss = epoch_loss / len(dataloader)
        print(f"--- Epoka {epoch+1}/{epochs} | Sredni loss: {avg_loss:.6f} ---")
        
        scheduler.step(avg_loss)
        
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(model.state_dict(), "sansamp_model.pth")
            print(f" -> Zapisano nowy, najlepszy model!")

if __name__ == "__main__":
    train()
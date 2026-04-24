import { useState } from 'react';
import { Upload, File } from 'lucide-react';

interface FileUploadZoneProps {
  onFilesUpload: (files: FileList) => void;
}

export function FileUploadZone({ onFilesUpload }: FileUploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onFilesUpload(e.dataTransfer.files);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onFilesUpload(e.target.files);
    }
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${
        isDragging
          ? 'border-indigo-500 bg-indigo-50'
          : 'border-gray-300 hover:border-indigo-400 bg-gray-50'
      }`}
    >
      <div className="flex flex-col items-center gap-3">
        <div className={`w-16 h-16 rounded-full flex items-center justify-center transition-colors ${
          isDragging ? 'bg-indigo-100' : 'bg-gray-100'
        }`}>
          {isDragging ? (
            <File className="w-8 h-8 text-indigo-600" />
          ) : (
            <Upload className="w-8 h-8 text-gray-400" />
          )}
        </div>
        <div>
          <p className="font-medium mb-1">
            {isDragging ? 'Drop your files here' : 'Drag & drop files here'}
          </p>
          <p className="text-sm text-gray-500">or</p>
        </div>
        <label className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors cursor-pointer">
          Browse Files
          <input
            type="file"
            multiple
            onChange={handleFileInput}
            className="hidden"
            accept=".csv,.xlsx,.xls,.json,.txt"
          />
        </label>
        <p className="text-xs text-gray-500 mt-2">
          Supported: CSV, Excel, JSON, TXT
        </p>
      </div>
    </div>
  );
}

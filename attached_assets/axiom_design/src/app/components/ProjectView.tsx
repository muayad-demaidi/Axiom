import { useState } from 'react';
import { ArrowLeft, FileText, X, FileSpreadsheet, File, Trash2 } from 'lucide-react';
import { FileUploadZone } from './FileUploadZone';
import { ChatInterface } from './ChatInterface';
import { ConnectionBanner } from './ConnectionBanner';

interface Project {
  id: string;
  name: string;
  description: string;
  fileCount: number;
  createdAt: string;
}

interface UploadedFile {
  id: string;
  name: string;
  size: string;
  type: string;
  file: File;
}

export function ProjectView({ project, onBack }: { project: Project; onBack: () => void }) {
  const [files, setFiles] = useState<UploadedFile[]>([]);

  const handleFilesUpload = (fileList: FileList) => {
    const newFiles: UploadedFile[] = Array.from(fileList).map((file) => ({
      id: Date.now().toString() + Math.random(),
      name: file.name,
      size: formatFileSize(file.size),
      type: file.name.split('.').pop()?.toLowerCase() || 'file',
      file: file
    }));

    setFiles([...files, ...newFiles]);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const handleRemoveFile = (fileId: string) => {
    setFiles(files.filter(f => f.id !== fileId));
  };

  const getFileIcon = (type: string) => {
    if (type === 'csv' || type === 'xlsx' || type === 'xls') {
      return <FileSpreadsheet className="w-5 h-5 text-green-600" />;
    }
    if (type === 'pdf') {
      return <FileText className="w-5 h-5 text-red-600" />;
    }
    if (type === 'json') {
      return <File className="w-5 h-5 text-blue-600" />;
    }
    return <File className="w-5 h-5 text-gray-600" />;
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1">
            <h1 className="font-bold text-xl">{project.name}</h1>
            <p className="text-sm text-gray-500">{project.description}</p>
          </div>
          <div className="text-right text-sm text-gray-500">
            <div>{files.length} files uploaded</div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar - File Upload & List */}
        <div className="w-96 bg-white border-r flex flex-col">
          <div className="p-4 space-y-4">
            <ConnectionBanner />

            {files.length === 0 ? (
              <FileUploadZone onFilesUpload={handleFilesUpload} />
            ) : (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-700">
                    Uploaded Files ({files.length})
                  </h3>
                  <label className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors cursor-pointer">
                    + Add
                    <input
                      type="file"
                      multiple
                      onChange={(e) => e.target.files && handleFilesUpload(e.target.files)}
                      className="hidden"
                      accept=".csv,.xlsx,.xls,.json,.txt"
                    />
                  </label>
                </div>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {files.map((file) => (
                    <div
                      key={file.id}
                      className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors group"
                    >
                      {getFileIcon(file.type)}
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm truncate">{file.name}</p>
                        <p className="text-xs text-gray-500">{file.size}</p>
                      </div>
                      <button
                        onClick={() => handleRemoveFile(file.id)}
                        className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-100 rounded transition-opacity"
                        title="Remove file"
                      >
                        <Trash2 className="w-4 h-4 text-red-600" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {files.length === 0 && (
              <div className="text-center py-8 text-gray-500 text-sm">
                <p>Upload your data files to start</p>
                <p className="mt-1">CSV, Excel, JSON, or TXT</p>
              </div>
            )}
          </div>
        </div>

        {/* Main Chat Area */}
        <div className="flex-1">
          <ChatInterface files={files} />
        </div>
      </div>
    </div>
  );
}

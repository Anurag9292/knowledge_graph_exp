'use client';

import { useState, useRef } from 'react';
import { FileText, Upload, ChevronDown, ChevronUp, X } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { documentsApi } from '@/lib/api';

export function DocumentInput() {
  const { inputText, setInputText, inputPanelOpen, toggleInputPanel, setInputDocumentPath } = useAppStore();
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const result = await documentsApi.upload(file);
      setInputText(result.raw_text);
      setUploadedFile(file.name);
      setInputDocumentPath(result.file_path);
    } catch (err) {
      console.error('Upload failed:', err);
    }
    setUploading(false);
  };

  const clearFile = () => {
    setUploadedFile(null);
    setInputDocumentPath(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  return (
    <div className={`border-t border-gray-200 bg-white transition-all ${inputPanelOpen ? 'h-48' : 'h-10'}`}>
      {/* Toggle bar */}
      <div
        className="h-10 flex items-center justify-between px-4 cursor-pointer hover:bg-gray-50"
        onClick={() => toggleInputPanel()}
      >
        <div className="flex items-center gap-2 text-xs font-medium text-gray-600">
          <FileText className="w-4 h-4" />
          <span>Document Input</span>
          {inputText && (
            <span className="text-gray-400">
              ({inputText.length} chars, {inputText.split(/\s+/).length} words)
            </span>
          )}
          {uploadedFile && (
            <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full text-xs flex items-center gap-1">
              📄 {uploadedFile}
              <button onClick={(e) => { e.stopPropagation(); clearFile(); }} className="hover:text-red-500">
                <X className="w-3 h-3" />
              </button>
            </span>
          )}
        </div>
        {inputPanelOpen ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronUp className="w-4 h-4 text-gray-400" />}
      </div>

      {/* Content */}
      {inputPanelOpen && (
        <div className="h-[calc(100%-2.5rem)] flex gap-3 px-4 pb-3">
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Paste your text here, or upload a document..."
            className="flex-1 text-xs border border-gray-300 rounded-md p-3 resize-none focus:outline-none focus:ring-1 focus:ring-blue-400 font-mono"
          />
          <div className="flex flex-col gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.pdf,.docx,.html"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200 disabled:opacity-50 transition whitespace-nowrap"
            >
              <Upload className="w-3.5 h-3.5" />
              {uploading ? 'Uploading...' : 'Upload File'}
            </button>
            <div className="text-xs text-gray-400 text-center">
              .txt .md .pdf<br />.docx .html
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

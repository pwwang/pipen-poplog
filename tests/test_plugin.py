import pytest
from unittest.mock import mock_open, patch
from pipen_poplog import PipenPoplogPlugin


class TestPipenPoplogPlugin:
    """Test cases for the PipenPoplogPlugin class."""

    def test_is_remote_filesystem_with_nfs(self):
        """Test detection of NFS filesystem."""
        plugin = PipenPoplogPlugin()
        
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\nserver:/export /mnt/nfs nfs4 rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            result = plugin._is_remote_filesystem("/mnt/nfs/test.log")
            assert result is True

    def test_is_remote_filesystem_with_fuse(self):
        """Test detection of FUSE filesystem (used by cloud storage)."""
        plugin = PipenPoplogPlugin()
        
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\ngcsfuse /mnt/gcs fuse rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            result = plugin._is_remote_filesystem("/mnt/gcs/test.log")
            assert result is True

    def test_is_remote_filesystem_with_cifs(self):
        """Test detection of CIFS/SMB filesystem."""
        plugin = PipenPoplogPlugin()
        
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\n//server/share /mnt/smb cifs rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            result = plugin._is_remote_filesystem("/mnt/smb/test.log")
            assert result is True

    def test_is_remote_filesystem_with_local_ext4(self):
        """Test that local ext4 filesystem is not detected as remote."""
        plugin = PipenPoplogPlugin()
        
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            result = plugin._is_remote_filesystem("/tmp/test.log")
            assert result is False

    def test_is_remote_filesystem_with_local_tmpfs(self):
        """Test that tmpfs is not detected as remote."""
        plugin = PipenPoplogPlugin()
        
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\ntmpfs /tmp tmpfs rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            result = plugin._is_remote_filesystem("/tmp/test.log")
            assert result is False

    def test_is_remote_filesystem_longest_match(self):
        """Test that the longest mount point match is used."""
        plugin = PipenPoplogPlugin()
        
        # / is ext4, but /mnt/nfs is nfs4
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\nserver:/export /mnt/nfs nfs4 rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            # File under /mnt/nfs should be detected as remote
            result = plugin._is_remote_filesystem("/mnt/nfs/subdir/test.log")
            assert result is True
            
            # File directly under / should not be remote
            result = plugin._is_remote_filesystem("/var/log/test.log")
            assert result is False

    def test_is_remote_filesystem_fallback_on_error(self):
        """Test fallback behavior when /proc/mounts can't be read."""
        plugin = PipenPoplogPlugin()
        
        with patch('builtins.open', side_effect=FileNotFoundError()):
            # Should fall back to checking path prefix
            result = plugin._is_remote_filesystem("/mnt/test.log")
            assert result is True
            
            result = plugin._is_remote_filesystem("/mount/test.log")
            assert result is True
            
            result = plugin._is_remote_filesystem("/tmp/test.log")
            assert result is False

    def test_is_remote_filesystem_with_s3fs(self):
        """Test detection of S3 filesystem with fuse variant."""
        plugin = PipenPoplogPlugin()
        
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\ns3fs /mnt/s3 fuse.s3fs rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            # fuse.s3fs should be detected as remote (FUSE variant)
            result = plugin._is_remote_filesystem("/mnt/s3/test.log")
            assert result is True

    def test_is_remote_filesystem_symlink_resolution(self):
        """Test that symlinks are resolved before checking."""
        plugin = PipenPoplogPlugin()
        
        mock_mounts = "/dev/sda1 / ext4 rw 0 0\nserver:/export /mnt/nfs nfs4 rw 0 0\n"
        
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            with patch('os.path.realpath', return_value='/mnt/nfs/real.log'):
                result = plugin._is_remote_filesystem("/tmp/symlink.log")
                assert result is True

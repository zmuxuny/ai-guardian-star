/* Orange Pi AI Pro headphone output, using the installed Ascend media ABI.
 * SYS init is per-process and idempotent; never exit SYS owned by camera/NPU code.
 */
#include <string.h>
#include "acl/media/hi_mpi_audio.h"
#include "acl/dvpp/hi_mpi_sys.h"

static int device_enabled;
static int channel_enabled;

void guardian_audio_close(void)
{
    if (channel_enabled) hi_mpi_ao_disable_chn(2, 0);
    if (device_enabled) hi_mpi_ao_disable(2);
    channel_enabled = device_enabled = 0;
}

int guardian_audio_open(void)
{
    int ret = hi_mpi_sys_init();
    if (ret) return ret;
    hi_aio_attr attr = {0};
    attr.sample_rate = HI_AUDIO_SAMPLE_RATE_48000;
    attr.bit_width = HI_AUDIO_BIT_WIDTH_16;
    attr.work_mode = HI_AIO_MODE_I2S_MASTER;
    attr.snd_mode = HI_AUDIO_SOUND_MODE_STEREO;
    attr.frame_num = 6;
    attr.point_num_per_frame = 960;
    attr.chn_cnt = 2;
    attr.clk_share = 1;
    attr.i2s_type = HI_AIO_I2STYPE_INNERCODEC;
    ret = hi_mpi_ao_set_pub_attr(2, &attr);
    if (ret) return ret;
    ret = hi_mpi_ao_enable(2);
    if (ret) return ret;
    device_enabled = 1;
    ret = hi_mpi_ao_enable_chn(2, 0);
    if (ret) { guardian_audio_close(); return ret; }
    channel_enabled = 1;
    return 0;
}

int guardian_audio_write(const void *pcm, unsigned int length)
{
    if (!channel_enabled || length != 1920) return -1;
    hi_audio_frame frame = {0};
    frame.bit_width = HI_AUDIO_BIT_WIDTH_16;
    frame.snd_mode = HI_AUDIO_SOUND_MODE_MONO;
    frame.virt_addr[0] = (hi_u8 *)pcm;
    frame.len = length;
    return hi_mpi_ao_send_frame(2, 0, &frame, 100);
}

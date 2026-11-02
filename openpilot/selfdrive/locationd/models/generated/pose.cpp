#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_2888912773465460112) {
   out_2888912773465460112[0] = delta_x[0] + nom_x[0];
   out_2888912773465460112[1] = delta_x[1] + nom_x[1];
   out_2888912773465460112[2] = delta_x[2] + nom_x[2];
   out_2888912773465460112[3] = delta_x[3] + nom_x[3];
   out_2888912773465460112[4] = delta_x[4] + nom_x[4];
   out_2888912773465460112[5] = delta_x[5] + nom_x[5];
   out_2888912773465460112[6] = delta_x[6] + nom_x[6];
   out_2888912773465460112[7] = delta_x[7] + nom_x[7];
   out_2888912773465460112[8] = delta_x[8] + nom_x[8];
   out_2888912773465460112[9] = delta_x[9] + nom_x[9];
   out_2888912773465460112[10] = delta_x[10] + nom_x[10];
   out_2888912773465460112[11] = delta_x[11] + nom_x[11];
   out_2888912773465460112[12] = delta_x[12] + nom_x[12];
   out_2888912773465460112[13] = delta_x[13] + nom_x[13];
   out_2888912773465460112[14] = delta_x[14] + nom_x[14];
   out_2888912773465460112[15] = delta_x[15] + nom_x[15];
   out_2888912773465460112[16] = delta_x[16] + nom_x[16];
   out_2888912773465460112[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_5859204138557633979) {
   out_5859204138557633979[0] = -nom_x[0] + true_x[0];
   out_5859204138557633979[1] = -nom_x[1] + true_x[1];
   out_5859204138557633979[2] = -nom_x[2] + true_x[2];
   out_5859204138557633979[3] = -nom_x[3] + true_x[3];
   out_5859204138557633979[4] = -nom_x[4] + true_x[4];
   out_5859204138557633979[5] = -nom_x[5] + true_x[5];
   out_5859204138557633979[6] = -nom_x[6] + true_x[6];
   out_5859204138557633979[7] = -nom_x[7] + true_x[7];
   out_5859204138557633979[8] = -nom_x[8] + true_x[8];
   out_5859204138557633979[9] = -nom_x[9] + true_x[9];
   out_5859204138557633979[10] = -nom_x[10] + true_x[10];
   out_5859204138557633979[11] = -nom_x[11] + true_x[11];
   out_5859204138557633979[12] = -nom_x[12] + true_x[12];
   out_5859204138557633979[13] = -nom_x[13] + true_x[13];
   out_5859204138557633979[14] = -nom_x[14] + true_x[14];
   out_5859204138557633979[15] = -nom_x[15] + true_x[15];
   out_5859204138557633979[16] = -nom_x[16] + true_x[16];
   out_5859204138557633979[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_5221902563181446422) {
   out_5221902563181446422[0] = 1.0;
   out_5221902563181446422[1] = 0.0;
   out_5221902563181446422[2] = 0.0;
   out_5221902563181446422[3] = 0.0;
   out_5221902563181446422[4] = 0.0;
   out_5221902563181446422[5] = 0.0;
   out_5221902563181446422[6] = 0.0;
   out_5221902563181446422[7] = 0.0;
   out_5221902563181446422[8] = 0.0;
   out_5221902563181446422[9] = 0.0;
   out_5221902563181446422[10] = 0.0;
   out_5221902563181446422[11] = 0.0;
   out_5221902563181446422[12] = 0.0;
   out_5221902563181446422[13] = 0.0;
   out_5221902563181446422[14] = 0.0;
   out_5221902563181446422[15] = 0.0;
   out_5221902563181446422[16] = 0.0;
   out_5221902563181446422[17] = 0.0;
   out_5221902563181446422[18] = 0.0;
   out_5221902563181446422[19] = 1.0;
   out_5221902563181446422[20] = 0.0;
   out_5221902563181446422[21] = 0.0;
   out_5221902563181446422[22] = 0.0;
   out_5221902563181446422[23] = 0.0;
   out_5221902563181446422[24] = 0.0;
   out_5221902563181446422[25] = 0.0;
   out_5221902563181446422[26] = 0.0;
   out_5221902563181446422[27] = 0.0;
   out_5221902563181446422[28] = 0.0;
   out_5221902563181446422[29] = 0.0;
   out_5221902563181446422[30] = 0.0;
   out_5221902563181446422[31] = 0.0;
   out_5221902563181446422[32] = 0.0;
   out_5221902563181446422[33] = 0.0;
   out_5221902563181446422[34] = 0.0;
   out_5221902563181446422[35] = 0.0;
   out_5221902563181446422[36] = 0.0;
   out_5221902563181446422[37] = 0.0;
   out_5221902563181446422[38] = 1.0;
   out_5221902563181446422[39] = 0.0;
   out_5221902563181446422[40] = 0.0;
   out_5221902563181446422[41] = 0.0;
   out_5221902563181446422[42] = 0.0;
   out_5221902563181446422[43] = 0.0;
   out_5221902563181446422[44] = 0.0;
   out_5221902563181446422[45] = 0.0;
   out_5221902563181446422[46] = 0.0;
   out_5221902563181446422[47] = 0.0;
   out_5221902563181446422[48] = 0.0;
   out_5221902563181446422[49] = 0.0;
   out_5221902563181446422[50] = 0.0;
   out_5221902563181446422[51] = 0.0;
   out_5221902563181446422[52] = 0.0;
   out_5221902563181446422[53] = 0.0;
   out_5221902563181446422[54] = 0.0;
   out_5221902563181446422[55] = 0.0;
   out_5221902563181446422[56] = 0.0;
   out_5221902563181446422[57] = 1.0;
   out_5221902563181446422[58] = 0.0;
   out_5221902563181446422[59] = 0.0;
   out_5221902563181446422[60] = 0.0;
   out_5221902563181446422[61] = 0.0;
   out_5221902563181446422[62] = 0.0;
   out_5221902563181446422[63] = 0.0;
   out_5221902563181446422[64] = 0.0;
   out_5221902563181446422[65] = 0.0;
   out_5221902563181446422[66] = 0.0;
   out_5221902563181446422[67] = 0.0;
   out_5221902563181446422[68] = 0.0;
   out_5221902563181446422[69] = 0.0;
   out_5221902563181446422[70] = 0.0;
   out_5221902563181446422[71] = 0.0;
   out_5221902563181446422[72] = 0.0;
   out_5221902563181446422[73] = 0.0;
   out_5221902563181446422[74] = 0.0;
   out_5221902563181446422[75] = 0.0;
   out_5221902563181446422[76] = 1.0;
   out_5221902563181446422[77] = 0.0;
   out_5221902563181446422[78] = 0.0;
   out_5221902563181446422[79] = 0.0;
   out_5221902563181446422[80] = 0.0;
   out_5221902563181446422[81] = 0.0;
   out_5221902563181446422[82] = 0.0;
   out_5221902563181446422[83] = 0.0;
   out_5221902563181446422[84] = 0.0;
   out_5221902563181446422[85] = 0.0;
   out_5221902563181446422[86] = 0.0;
   out_5221902563181446422[87] = 0.0;
   out_5221902563181446422[88] = 0.0;
   out_5221902563181446422[89] = 0.0;
   out_5221902563181446422[90] = 0.0;
   out_5221902563181446422[91] = 0.0;
   out_5221902563181446422[92] = 0.0;
   out_5221902563181446422[93] = 0.0;
   out_5221902563181446422[94] = 0.0;
   out_5221902563181446422[95] = 1.0;
   out_5221902563181446422[96] = 0.0;
   out_5221902563181446422[97] = 0.0;
   out_5221902563181446422[98] = 0.0;
   out_5221902563181446422[99] = 0.0;
   out_5221902563181446422[100] = 0.0;
   out_5221902563181446422[101] = 0.0;
   out_5221902563181446422[102] = 0.0;
   out_5221902563181446422[103] = 0.0;
   out_5221902563181446422[104] = 0.0;
   out_5221902563181446422[105] = 0.0;
   out_5221902563181446422[106] = 0.0;
   out_5221902563181446422[107] = 0.0;
   out_5221902563181446422[108] = 0.0;
   out_5221902563181446422[109] = 0.0;
   out_5221902563181446422[110] = 0.0;
   out_5221902563181446422[111] = 0.0;
   out_5221902563181446422[112] = 0.0;
   out_5221902563181446422[113] = 0.0;
   out_5221902563181446422[114] = 1.0;
   out_5221902563181446422[115] = 0.0;
   out_5221902563181446422[116] = 0.0;
   out_5221902563181446422[117] = 0.0;
   out_5221902563181446422[118] = 0.0;
   out_5221902563181446422[119] = 0.0;
   out_5221902563181446422[120] = 0.0;
   out_5221902563181446422[121] = 0.0;
   out_5221902563181446422[122] = 0.0;
   out_5221902563181446422[123] = 0.0;
   out_5221902563181446422[124] = 0.0;
   out_5221902563181446422[125] = 0.0;
   out_5221902563181446422[126] = 0.0;
   out_5221902563181446422[127] = 0.0;
   out_5221902563181446422[128] = 0.0;
   out_5221902563181446422[129] = 0.0;
   out_5221902563181446422[130] = 0.0;
   out_5221902563181446422[131] = 0.0;
   out_5221902563181446422[132] = 0.0;
   out_5221902563181446422[133] = 1.0;
   out_5221902563181446422[134] = 0.0;
   out_5221902563181446422[135] = 0.0;
   out_5221902563181446422[136] = 0.0;
   out_5221902563181446422[137] = 0.0;
   out_5221902563181446422[138] = 0.0;
   out_5221902563181446422[139] = 0.0;
   out_5221902563181446422[140] = 0.0;
   out_5221902563181446422[141] = 0.0;
   out_5221902563181446422[142] = 0.0;
   out_5221902563181446422[143] = 0.0;
   out_5221902563181446422[144] = 0.0;
   out_5221902563181446422[145] = 0.0;
   out_5221902563181446422[146] = 0.0;
   out_5221902563181446422[147] = 0.0;
   out_5221902563181446422[148] = 0.0;
   out_5221902563181446422[149] = 0.0;
   out_5221902563181446422[150] = 0.0;
   out_5221902563181446422[151] = 0.0;
   out_5221902563181446422[152] = 1.0;
   out_5221902563181446422[153] = 0.0;
   out_5221902563181446422[154] = 0.0;
   out_5221902563181446422[155] = 0.0;
   out_5221902563181446422[156] = 0.0;
   out_5221902563181446422[157] = 0.0;
   out_5221902563181446422[158] = 0.0;
   out_5221902563181446422[159] = 0.0;
   out_5221902563181446422[160] = 0.0;
   out_5221902563181446422[161] = 0.0;
   out_5221902563181446422[162] = 0.0;
   out_5221902563181446422[163] = 0.0;
   out_5221902563181446422[164] = 0.0;
   out_5221902563181446422[165] = 0.0;
   out_5221902563181446422[166] = 0.0;
   out_5221902563181446422[167] = 0.0;
   out_5221902563181446422[168] = 0.0;
   out_5221902563181446422[169] = 0.0;
   out_5221902563181446422[170] = 0.0;
   out_5221902563181446422[171] = 1.0;
   out_5221902563181446422[172] = 0.0;
   out_5221902563181446422[173] = 0.0;
   out_5221902563181446422[174] = 0.0;
   out_5221902563181446422[175] = 0.0;
   out_5221902563181446422[176] = 0.0;
   out_5221902563181446422[177] = 0.0;
   out_5221902563181446422[178] = 0.0;
   out_5221902563181446422[179] = 0.0;
   out_5221902563181446422[180] = 0.0;
   out_5221902563181446422[181] = 0.0;
   out_5221902563181446422[182] = 0.0;
   out_5221902563181446422[183] = 0.0;
   out_5221902563181446422[184] = 0.0;
   out_5221902563181446422[185] = 0.0;
   out_5221902563181446422[186] = 0.0;
   out_5221902563181446422[187] = 0.0;
   out_5221902563181446422[188] = 0.0;
   out_5221902563181446422[189] = 0.0;
   out_5221902563181446422[190] = 1.0;
   out_5221902563181446422[191] = 0.0;
   out_5221902563181446422[192] = 0.0;
   out_5221902563181446422[193] = 0.0;
   out_5221902563181446422[194] = 0.0;
   out_5221902563181446422[195] = 0.0;
   out_5221902563181446422[196] = 0.0;
   out_5221902563181446422[197] = 0.0;
   out_5221902563181446422[198] = 0.0;
   out_5221902563181446422[199] = 0.0;
   out_5221902563181446422[200] = 0.0;
   out_5221902563181446422[201] = 0.0;
   out_5221902563181446422[202] = 0.0;
   out_5221902563181446422[203] = 0.0;
   out_5221902563181446422[204] = 0.0;
   out_5221902563181446422[205] = 0.0;
   out_5221902563181446422[206] = 0.0;
   out_5221902563181446422[207] = 0.0;
   out_5221902563181446422[208] = 0.0;
   out_5221902563181446422[209] = 1.0;
   out_5221902563181446422[210] = 0.0;
   out_5221902563181446422[211] = 0.0;
   out_5221902563181446422[212] = 0.0;
   out_5221902563181446422[213] = 0.0;
   out_5221902563181446422[214] = 0.0;
   out_5221902563181446422[215] = 0.0;
   out_5221902563181446422[216] = 0.0;
   out_5221902563181446422[217] = 0.0;
   out_5221902563181446422[218] = 0.0;
   out_5221902563181446422[219] = 0.0;
   out_5221902563181446422[220] = 0.0;
   out_5221902563181446422[221] = 0.0;
   out_5221902563181446422[222] = 0.0;
   out_5221902563181446422[223] = 0.0;
   out_5221902563181446422[224] = 0.0;
   out_5221902563181446422[225] = 0.0;
   out_5221902563181446422[226] = 0.0;
   out_5221902563181446422[227] = 0.0;
   out_5221902563181446422[228] = 1.0;
   out_5221902563181446422[229] = 0.0;
   out_5221902563181446422[230] = 0.0;
   out_5221902563181446422[231] = 0.0;
   out_5221902563181446422[232] = 0.0;
   out_5221902563181446422[233] = 0.0;
   out_5221902563181446422[234] = 0.0;
   out_5221902563181446422[235] = 0.0;
   out_5221902563181446422[236] = 0.0;
   out_5221902563181446422[237] = 0.0;
   out_5221902563181446422[238] = 0.0;
   out_5221902563181446422[239] = 0.0;
   out_5221902563181446422[240] = 0.0;
   out_5221902563181446422[241] = 0.0;
   out_5221902563181446422[242] = 0.0;
   out_5221902563181446422[243] = 0.0;
   out_5221902563181446422[244] = 0.0;
   out_5221902563181446422[245] = 0.0;
   out_5221902563181446422[246] = 0.0;
   out_5221902563181446422[247] = 1.0;
   out_5221902563181446422[248] = 0.0;
   out_5221902563181446422[249] = 0.0;
   out_5221902563181446422[250] = 0.0;
   out_5221902563181446422[251] = 0.0;
   out_5221902563181446422[252] = 0.0;
   out_5221902563181446422[253] = 0.0;
   out_5221902563181446422[254] = 0.0;
   out_5221902563181446422[255] = 0.0;
   out_5221902563181446422[256] = 0.0;
   out_5221902563181446422[257] = 0.0;
   out_5221902563181446422[258] = 0.0;
   out_5221902563181446422[259] = 0.0;
   out_5221902563181446422[260] = 0.0;
   out_5221902563181446422[261] = 0.0;
   out_5221902563181446422[262] = 0.0;
   out_5221902563181446422[263] = 0.0;
   out_5221902563181446422[264] = 0.0;
   out_5221902563181446422[265] = 0.0;
   out_5221902563181446422[266] = 1.0;
   out_5221902563181446422[267] = 0.0;
   out_5221902563181446422[268] = 0.0;
   out_5221902563181446422[269] = 0.0;
   out_5221902563181446422[270] = 0.0;
   out_5221902563181446422[271] = 0.0;
   out_5221902563181446422[272] = 0.0;
   out_5221902563181446422[273] = 0.0;
   out_5221902563181446422[274] = 0.0;
   out_5221902563181446422[275] = 0.0;
   out_5221902563181446422[276] = 0.0;
   out_5221902563181446422[277] = 0.0;
   out_5221902563181446422[278] = 0.0;
   out_5221902563181446422[279] = 0.0;
   out_5221902563181446422[280] = 0.0;
   out_5221902563181446422[281] = 0.0;
   out_5221902563181446422[282] = 0.0;
   out_5221902563181446422[283] = 0.0;
   out_5221902563181446422[284] = 0.0;
   out_5221902563181446422[285] = 1.0;
   out_5221902563181446422[286] = 0.0;
   out_5221902563181446422[287] = 0.0;
   out_5221902563181446422[288] = 0.0;
   out_5221902563181446422[289] = 0.0;
   out_5221902563181446422[290] = 0.0;
   out_5221902563181446422[291] = 0.0;
   out_5221902563181446422[292] = 0.0;
   out_5221902563181446422[293] = 0.0;
   out_5221902563181446422[294] = 0.0;
   out_5221902563181446422[295] = 0.0;
   out_5221902563181446422[296] = 0.0;
   out_5221902563181446422[297] = 0.0;
   out_5221902563181446422[298] = 0.0;
   out_5221902563181446422[299] = 0.0;
   out_5221902563181446422[300] = 0.0;
   out_5221902563181446422[301] = 0.0;
   out_5221902563181446422[302] = 0.0;
   out_5221902563181446422[303] = 0.0;
   out_5221902563181446422[304] = 1.0;
   out_5221902563181446422[305] = 0.0;
   out_5221902563181446422[306] = 0.0;
   out_5221902563181446422[307] = 0.0;
   out_5221902563181446422[308] = 0.0;
   out_5221902563181446422[309] = 0.0;
   out_5221902563181446422[310] = 0.0;
   out_5221902563181446422[311] = 0.0;
   out_5221902563181446422[312] = 0.0;
   out_5221902563181446422[313] = 0.0;
   out_5221902563181446422[314] = 0.0;
   out_5221902563181446422[315] = 0.0;
   out_5221902563181446422[316] = 0.0;
   out_5221902563181446422[317] = 0.0;
   out_5221902563181446422[318] = 0.0;
   out_5221902563181446422[319] = 0.0;
   out_5221902563181446422[320] = 0.0;
   out_5221902563181446422[321] = 0.0;
   out_5221902563181446422[322] = 0.0;
   out_5221902563181446422[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_1175449659287803657) {
   out_1175449659287803657[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_1175449659287803657[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_1175449659287803657[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_1175449659287803657[3] = dt*state[12] + state[3];
   out_1175449659287803657[4] = dt*state[13] + state[4];
   out_1175449659287803657[5] = dt*state[14] + state[5];
   out_1175449659287803657[6] = state[6];
   out_1175449659287803657[7] = state[7];
   out_1175449659287803657[8] = state[8];
   out_1175449659287803657[9] = state[9];
   out_1175449659287803657[10] = state[10];
   out_1175449659287803657[11] = state[11];
   out_1175449659287803657[12] = state[12];
   out_1175449659287803657[13] = state[13];
   out_1175449659287803657[14] = state[14];
   out_1175449659287803657[15] = state[15];
   out_1175449659287803657[16] = state[16];
   out_1175449659287803657[17] = state[17];
}
void F_fun(double *state, double dt, double *out_1771814395118668150) {
   out_1771814395118668150[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1771814395118668150[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1771814395118668150[2] = 0;
   out_1771814395118668150[3] = 0;
   out_1771814395118668150[4] = 0;
   out_1771814395118668150[5] = 0;
   out_1771814395118668150[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1771814395118668150[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1771814395118668150[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1771814395118668150[9] = 0;
   out_1771814395118668150[10] = 0;
   out_1771814395118668150[11] = 0;
   out_1771814395118668150[12] = 0;
   out_1771814395118668150[13] = 0;
   out_1771814395118668150[14] = 0;
   out_1771814395118668150[15] = 0;
   out_1771814395118668150[16] = 0;
   out_1771814395118668150[17] = 0;
   out_1771814395118668150[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1771814395118668150[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1771814395118668150[20] = 0;
   out_1771814395118668150[21] = 0;
   out_1771814395118668150[22] = 0;
   out_1771814395118668150[23] = 0;
   out_1771814395118668150[24] = 0;
   out_1771814395118668150[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1771814395118668150[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1771814395118668150[27] = 0;
   out_1771814395118668150[28] = 0;
   out_1771814395118668150[29] = 0;
   out_1771814395118668150[30] = 0;
   out_1771814395118668150[31] = 0;
   out_1771814395118668150[32] = 0;
   out_1771814395118668150[33] = 0;
   out_1771814395118668150[34] = 0;
   out_1771814395118668150[35] = 0;
   out_1771814395118668150[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1771814395118668150[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1771814395118668150[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1771814395118668150[39] = 0;
   out_1771814395118668150[40] = 0;
   out_1771814395118668150[41] = 0;
   out_1771814395118668150[42] = 0;
   out_1771814395118668150[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1771814395118668150[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1771814395118668150[45] = 0;
   out_1771814395118668150[46] = 0;
   out_1771814395118668150[47] = 0;
   out_1771814395118668150[48] = 0;
   out_1771814395118668150[49] = 0;
   out_1771814395118668150[50] = 0;
   out_1771814395118668150[51] = 0;
   out_1771814395118668150[52] = 0;
   out_1771814395118668150[53] = 0;
   out_1771814395118668150[54] = 0;
   out_1771814395118668150[55] = 0;
   out_1771814395118668150[56] = 0;
   out_1771814395118668150[57] = 1;
   out_1771814395118668150[58] = 0;
   out_1771814395118668150[59] = 0;
   out_1771814395118668150[60] = 0;
   out_1771814395118668150[61] = 0;
   out_1771814395118668150[62] = 0;
   out_1771814395118668150[63] = 0;
   out_1771814395118668150[64] = 0;
   out_1771814395118668150[65] = 0;
   out_1771814395118668150[66] = dt;
   out_1771814395118668150[67] = 0;
   out_1771814395118668150[68] = 0;
   out_1771814395118668150[69] = 0;
   out_1771814395118668150[70] = 0;
   out_1771814395118668150[71] = 0;
   out_1771814395118668150[72] = 0;
   out_1771814395118668150[73] = 0;
   out_1771814395118668150[74] = 0;
   out_1771814395118668150[75] = 0;
   out_1771814395118668150[76] = 1;
   out_1771814395118668150[77] = 0;
   out_1771814395118668150[78] = 0;
   out_1771814395118668150[79] = 0;
   out_1771814395118668150[80] = 0;
   out_1771814395118668150[81] = 0;
   out_1771814395118668150[82] = 0;
   out_1771814395118668150[83] = 0;
   out_1771814395118668150[84] = 0;
   out_1771814395118668150[85] = dt;
   out_1771814395118668150[86] = 0;
   out_1771814395118668150[87] = 0;
   out_1771814395118668150[88] = 0;
   out_1771814395118668150[89] = 0;
   out_1771814395118668150[90] = 0;
   out_1771814395118668150[91] = 0;
   out_1771814395118668150[92] = 0;
   out_1771814395118668150[93] = 0;
   out_1771814395118668150[94] = 0;
   out_1771814395118668150[95] = 1;
   out_1771814395118668150[96] = 0;
   out_1771814395118668150[97] = 0;
   out_1771814395118668150[98] = 0;
   out_1771814395118668150[99] = 0;
   out_1771814395118668150[100] = 0;
   out_1771814395118668150[101] = 0;
   out_1771814395118668150[102] = 0;
   out_1771814395118668150[103] = 0;
   out_1771814395118668150[104] = dt;
   out_1771814395118668150[105] = 0;
   out_1771814395118668150[106] = 0;
   out_1771814395118668150[107] = 0;
   out_1771814395118668150[108] = 0;
   out_1771814395118668150[109] = 0;
   out_1771814395118668150[110] = 0;
   out_1771814395118668150[111] = 0;
   out_1771814395118668150[112] = 0;
   out_1771814395118668150[113] = 0;
   out_1771814395118668150[114] = 1;
   out_1771814395118668150[115] = 0;
   out_1771814395118668150[116] = 0;
   out_1771814395118668150[117] = 0;
   out_1771814395118668150[118] = 0;
   out_1771814395118668150[119] = 0;
   out_1771814395118668150[120] = 0;
   out_1771814395118668150[121] = 0;
   out_1771814395118668150[122] = 0;
   out_1771814395118668150[123] = 0;
   out_1771814395118668150[124] = 0;
   out_1771814395118668150[125] = 0;
   out_1771814395118668150[126] = 0;
   out_1771814395118668150[127] = 0;
   out_1771814395118668150[128] = 0;
   out_1771814395118668150[129] = 0;
   out_1771814395118668150[130] = 0;
   out_1771814395118668150[131] = 0;
   out_1771814395118668150[132] = 0;
   out_1771814395118668150[133] = 1;
   out_1771814395118668150[134] = 0;
   out_1771814395118668150[135] = 0;
   out_1771814395118668150[136] = 0;
   out_1771814395118668150[137] = 0;
   out_1771814395118668150[138] = 0;
   out_1771814395118668150[139] = 0;
   out_1771814395118668150[140] = 0;
   out_1771814395118668150[141] = 0;
   out_1771814395118668150[142] = 0;
   out_1771814395118668150[143] = 0;
   out_1771814395118668150[144] = 0;
   out_1771814395118668150[145] = 0;
   out_1771814395118668150[146] = 0;
   out_1771814395118668150[147] = 0;
   out_1771814395118668150[148] = 0;
   out_1771814395118668150[149] = 0;
   out_1771814395118668150[150] = 0;
   out_1771814395118668150[151] = 0;
   out_1771814395118668150[152] = 1;
   out_1771814395118668150[153] = 0;
   out_1771814395118668150[154] = 0;
   out_1771814395118668150[155] = 0;
   out_1771814395118668150[156] = 0;
   out_1771814395118668150[157] = 0;
   out_1771814395118668150[158] = 0;
   out_1771814395118668150[159] = 0;
   out_1771814395118668150[160] = 0;
   out_1771814395118668150[161] = 0;
   out_1771814395118668150[162] = 0;
   out_1771814395118668150[163] = 0;
   out_1771814395118668150[164] = 0;
   out_1771814395118668150[165] = 0;
   out_1771814395118668150[166] = 0;
   out_1771814395118668150[167] = 0;
   out_1771814395118668150[168] = 0;
   out_1771814395118668150[169] = 0;
   out_1771814395118668150[170] = 0;
   out_1771814395118668150[171] = 1;
   out_1771814395118668150[172] = 0;
   out_1771814395118668150[173] = 0;
   out_1771814395118668150[174] = 0;
   out_1771814395118668150[175] = 0;
   out_1771814395118668150[176] = 0;
   out_1771814395118668150[177] = 0;
   out_1771814395118668150[178] = 0;
   out_1771814395118668150[179] = 0;
   out_1771814395118668150[180] = 0;
   out_1771814395118668150[181] = 0;
   out_1771814395118668150[182] = 0;
   out_1771814395118668150[183] = 0;
   out_1771814395118668150[184] = 0;
   out_1771814395118668150[185] = 0;
   out_1771814395118668150[186] = 0;
   out_1771814395118668150[187] = 0;
   out_1771814395118668150[188] = 0;
   out_1771814395118668150[189] = 0;
   out_1771814395118668150[190] = 1;
   out_1771814395118668150[191] = 0;
   out_1771814395118668150[192] = 0;
   out_1771814395118668150[193] = 0;
   out_1771814395118668150[194] = 0;
   out_1771814395118668150[195] = 0;
   out_1771814395118668150[196] = 0;
   out_1771814395118668150[197] = 0;
   out_1771814395118668150[198] = 0;
   out_1771814395118668150[199] = 0;
   out_1771814395118668150[200] = 0;
   out_1771814395118668150[201] = 0;
   out_1771814395118668150[202] = 0;
   out_1771814395118668150[203] = 0;
   out_1771814395118668150[204] = 0;
   out_1771814395118668150[205] = 0;
   out_1771814395118668150[206] = 0;
   out_1771814395118668150[207] = 0;
   out_1771814395118668150[208] = 0;
   out_1771814395118668150[209] = 1;
   out_1771814395118668150[210] = 0;
   out_1771814395118668150[211] = 0;
   out_1771814395118668150[212] = 0;
   out_1771814395118668150[213] = 0;
   out_1771814395118668150[214] = 0;
   out_1771814395118668150[215] = 0;
   out_1771814395118668150[216] = 0;
   out_1771814395118668150[217] = 0;
   out_1771814395118668150[218] = 0;
   out_1771814395118668150[219] = 0;
   out_1771814395118668150[220] = 0;
   out_1771814395118668150[221] = 0;
   out_1771814395118668150[222] = 0;
   out_1771814395118668150[223] = 0;
   out_1771814395118668150[224] = 0;
   out_1771814395118668150[225] = 0;
   out_1771814395118668150[226] = 0;
   out_1771814395118668150[227] = 0;
   out_1771814395118668150[228] = 1;
   out_1771814395118668150[229] = 0;
   out_1771814395118668150[230] = 0;
   out_1771814395118668150[231] = 0;
   out_1771814395118668150[232] = 0;
   out_1771814395118668150[233] = 0;
   out_1771814395118668150[234] = 0;
   out_1771814395118668150[235] = 0;
   out_1771814395118668150[236] = 0;
   out_1771814395118668150[237] = 0;
   out_1771814395118668150[238] = 0;
   out_1771814395118668150[239] = 0;
   out_1771814395118668150[240] = 0;
   out_1771814395118668150[241] = 0;
   out_1771814395118668150[242] = 0;
   out_1771814395118668150[243] = 0;
   out_1771814395118668150[244] = 0;
   out_1771814395118668150[245] = 0;
   out_1771814395118668150[246] = 0;
   out_1771814395118668150[247] = 1;
   out_1771814395118668150[248] = 0;
   out_1771814395118668150[249] = 0;
   out_1771814395118668150[250] = 0;
   out_1771814395118668150[251] = 0;
   out_1771814395118668150[252] = 0;
   out_1771814395118668150[253] = 0;
   out_1771814395118668150[254] = 0;
   out_1771814395118668150[255] = 0;
   out_1771814395118668150[256] = 0;
   out_1771814395118668150[257] = 0;
   out_1771814395118668150[258] = 0;
   out_1771814395118668150[259] = 0;
   out_1771814395118668150[260] = 0;
   out_1771814395118668150[261] = 0;
   out_1771814395118668150[262] = 0;
   out_1771814395118668150[263] = 0;
   out_1771814395118668150[264] = 0;
   out_1771814395118668150[265] = 0;
   out_1771814395118668150[266] = 1;
   out_1771814395118668150[267] = 0;
   out_1771814395118668150[268] = 0;
   out_1771814395118668150[269] = 0;
   out_1771814395118668150[270] = 0;
   out_1771814395118668150[271] = 0;
   out_1771814395118668150[272] = 0;
   out_1771814395118668150[273] = 0;
   out_1771814395118668150[274] = 0;
   out_1771814395118668150[275] = 0;
   out_1771814395118668150[276] = 0;
   out_1771814395118668150[277] = 0;
   out_1771814395118668150[278] = 0;
   out_1771814395118668150[279] = 0;
   out_1771814395118668150[280] = 0;
   out_1771814395118668150[281] = 0;
   out_1771814395118668150[282] = 0;
   out_1771814395118668150[283] = 0;
   out_1771814395118668150[284] = 0;
   out_1771814395118668150[285] = 1;
   out_1771814395118668150[286] = 0;
   out_1771814395118668150[287] = 0;
   out_1771814395118668150[288] = 0;
   out_1771814395118668150[289] = 0;
   out_1771814395118668150[290] = 0;
   out_1771814395118668150[291] = 0;
   out_1771814395118668150[292] = 0;
   out_1771814395118668150[293] = 0;
   out_1771814395118668150[294] = 0;
   out_1771814395118668150[295] = 0;
   out_1771814395118668150[296] = 0;
   out_1771814395118668150[297] = 0;
   out_1771814395118668150[298] = 0;
   out_1771814395118668150[299] = 0;
   out_1771814395118668150[300] = 0;
   out_1771814395118668150[301] = 0;
   out_1771814395118668150[302] = 0;
   out_1771814395118668150[303] = 0;
   out_1771814395118668150[304] = 1;
   out_1771814395118668150[305] = 0;
   out_1771814395118668150[306] = 0;
   out_1771814395118668150[307] = 0;
   out_1771814395118668150[308] = 0;
   out_1771814395118668150[309] = 0;
   out_1771814395118668150[310] = 0;
   out_1771814395118668150[311] = 0;
   out_1771814395118668150[312] = 0;
   out_1771814395118668150[313] = 0;
   out_1771814395118668150[314] = 0;
   out_1771814395118668150[315] = 0;
   out_1771814395118668150[316] = 0;
   out_1771814395118668150[317] = 0;
   out_1771814395118668150[318] = 0;
   out_1771814395118668150[319] = 0;
   out_1771814395118668150[320] = 0;
   out_1771814395118668150[321] = 0;
   out_1771814395118668150[322] = 0;
   out_1771814395118668150[323] = 1;
}
void h_4(double *state, double *unused, double *out_6579517944273218715) {
   out_6579517944273218715[0] = state[6] + state[9];
   out_6579517944273218715[1] = state[7] + state[10];
   out_6579517944273218715[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_626179243570512299) {
   out_626179243570512299[0] = 0;
   out_626179243570512299[1] = 0;
   out_626179243570512299[2] = 0;
   out_626179243570512299[3] = 0;
   out_626179243570512299[4] = 0;
   out_626179243570512299[5] = 0;
   out_626179243570512299[6] = 1;
   out_626179243570512299[7] = 0;
   out_626179243570512299[8] = 0;
   out_626179243570512299[9] = 1;
   out_626179243570512299[10] = 0;
   out_626179243570512299[11] = 0;
   out_626179243570512299[12] = 0;
   out_626179243570512299[13] = 0;
   out_626179243570512299[14] = 0;
   out_626179243570512299[15] = 0;
   out_626179243570512299[16] = 0;
   out_626179243570512299[17] = 0;
   out_626179243570512299[18] = 0;
   out_626179243570512299[19] = 0;
   out_626179243570512299[20] = 0;
   out_626179243570512299[21] = 0;
   out_626179243570512299[22] = 0;
   out_626179243570512299[23] = 0;
   out_626179243570512299[24] = 0;
   out_626179243570512299[25] = 1;
   out_626179243570512299[26] = 0;
   out_626179243570512299[27] = 0;
   out_626179243570512299[28] = 1;
   out_626179243570512299[29] = 0;
   out_626179243570512299[30] = 0;
   out_626179243570512299[31] = 0;
   out_626179243570512299[32] = 0;
   out_626179243570512299[33] = 0;
   out_626179243570512299[34] = 0;
   out_626179243570512299[35] = 0;
   out_626179243570512299[36] = 0;
   out_626179243570512299[37] = 0;
   out_626179243570512299[38] = 0;
   out_626179243570512299[39] = 0;
   out_626179243570512299[40] = 0;
   out_626179243570512299[41] = 0;
   out_626179243570512299[42] = 0;
   out_626179243570512299[43] = 0;
   out_626179243570512299[44] = 1;
   out_626179243570512299[45] = 0;
   out_626179243570512299[46] = 0;
   out_626179243570512299[47] = 1;
   out_626179243570512299[48] = 0;
   out_626179243570512299[49] = 0;
   out_626179243570512299[50] = 0;
   out_626179243570512299[51] = 0;
   out_626179243570512299[52] = 0;
   out_626179243570512299[53] = 0;
}
void h_10(double *state, double *unused, double *out_1705430589688773801) {
   out_1705430589688773801[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_1705430589688773801[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_1705430589688773801[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_7777681021109994334) {
   out_7777681021109994334[0] = 0;
   out_7777681021109994334[1] = 9.8100000000000005*cos(state[1]);
   out_7777681021109994334[2] = 0;
   out_7777681021109994334[3] = 0;
   out_7777681021109994334[4] = -state[8];
   out_7777681021109994334[5] = state[7];
   out_7777681021109994334[6] = 0;
   out_7777681021109994334[7] = state[5];
   out_7777681021109994334[8] = -state[4];
   out_7777681021109994334[9] = 0;
   out_7777681021109994334[10] = 0;
   out_7777681021109994334[11] = 0;
   out_7777681021109994334[12] = 1;
   out_7777681021109994334[13] = 0;
   out_7777681021109994334[14] = 0;
   out_7777681021109994334[15] = 1;
   out_7777681021109994334[16] = 0;
   out_7777681021109994334[17] = 0;
   out_7777681021109994334[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_7777681021109994334[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_7777681021109994334[20] = 0;
   out_7777681021109994334[21] = state[8];
   out_7777681021109994334[22] = 0;
   out_7777681021109994334[23] = -state[6];
   out_7777681021109994334[24] = -state[5];
   out_7777681021109994334[25] = 0;
   out_7777681021109994334[26] = state[3];
   out_7777681021109994334[27] = 0;
   out_7777681021109994334[28] = 0;
   out_7777681021109994334[29] = 0;
   out_7777681021109994334[30] = 0;
   out_7777681021109994334[31] = 1;
   out_7777681021109994334[32] = 0;
   out_7777681021109994334[33] = 0;
   out_7777681021109994334[34] = 1;
   out_7777681021109994334[35] = 0;
   out_7777681021109994334[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_7777681021109994334[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_7777681021109994334[38] = 0;
   out_7777681021109994334[39] = -state[7];
   out_7777681021109994334[40] = state[6];
   out_7777681021109994334[41] = 0;
   out_7777681021109994334[42] = state[4];
   out_7777681021109994334[43] = -state[3];
   out_7777681021109994334[44] = 0;
   out_7777681021109994334[45] = 0;
   out_7777681021109994334[46] = 0;
   out_7777681021109994334[47] = 0;
   out_7777681021109994334[48] = 0;
   out_7777681021109994334[49] = 0;
   out_7777681021109994334[50] = 1;
   out_7777681021109994334[51] = 0;
   out_7777681021109994334[52] = 0;
   out_7777681021109994334[53] = 1;
}
void h_13(double *state, double *unused, double *out_5206051105996912215) {
   out_5206051105996912215[0] = state[3];
   out_5206051105996912215[1] = state[4];
   out_5206051105996912215[2] = state[5];
}
void H_13(double *state, double *unused, double *out_2586094581761820502) {
   out_2586094581761820502[0] = 0;
   out_2586094581761820502[1] = 0;
   out_2586094581761820502[2] = 0;
   out_2586094581761820502[3] = 1;
   out_2586094581761820502[4] = 0;
   out_2586094581761820502[5] = 0;
   out_2586094581761820502[6] = 0;
   out_2586094581761820502[7] = 0;
   out_2586094581761820502[8] = 0;
   out_2586094581761820502[9] = 0;
   out_2586094581761820502[10] = 0;
   out_2586094581761820502[11] = 0;
   out_2586094581761820502[12] = 0;
   out_2586094581761820502[13] = 0;
   out_2586094581761820502[14] = 0;
   out_2586094581761820502[15] = 0;
   out_2586094581761820502[16] = 0;
   out_2586094581761820502[17] = 0;
   out_2586094581761820502[18] = 0;
   out_2586094581761820502[19] = 0;
   out_2586094581761820502[20] = 0;
   out_2586094581761820502[21] = 0;
   out_2586094581761820502[22] = 1;
   out_2586094581761820502[23] = 0;
   out_2586094581761820502[24] = 0;
   out_2586094581761820502[25] = 0;
   out_2586094581761820502[26] = 0;
   out_2586094581761820502[27] = 0;
   out_2586094581761820502[28] = 0;
   out_2586094581761820502[29] = 0;
   out_2586094581761820502[30] = 0;
   out_2586094581761820502[31] = 0;
   out_2586094581761820502[32] = 0;
   out_2586094581761820502[33] = 0;
   out_2586094581761820502[34] = 0;
   out_2586094581761820502[35] = 0;
   out_2586094581761820502[36] = 0;
   out_2586094581761820502[37] = 0;
   out_2586094581761820502[38] = 0;
   out_2586094581761820502[39] = 0;
   out_2586094581761820502[40] = 0;
   out_2586094581761820502[41] = 1;
   out_2586094581761820502[42] = 0;
   out_2586094581761820502[43] = 0;
   out_2586094581761820502[44] = 0;
   out_2586094581761820502[45] = 0;
   out_2586094581761820502[46] = 0;
   out_2586094581761820502[47] = 0;
   out_2586094581761820502[48] = 0;
   out_2586094581761820502[49] = 0;
   out_2586094581761820502[50] = 0;
   out_2586094581761820502[51] = 0;
   out_2586094581761820502[52] = 0;
   out_2586094581761820502[53] = 0;
}
void h_14(double *state, double *unused, double *out_9171638683540642626) {
   out_9171638683540642626[0] = state[6];
   out_9171638683540642626[1] = state[7];
   out_9171638683540642626[2] = state[8];
}
void H_14(double *state, double *unused, double *out_1061295770215395898) {
   out_1061295770215395898[0] = 0;
   out_1061295770215395898[1] = 0;
   out_1061295770215395898[2] = 0;
   out_1061295770215395898[3] = 0;
   out_1061295770215395898[4] = 0;
   out_1061295770215395898[5] = 0;
   out_1061295770215395898[6] = 1;
   out_1061295770215395898[7] = 0;
   out_1061295770215395898[8] = 0;
   out_1061295770215395898[9] = 0;
   out_1061295770215395898[10] = 0;
   out_1061295770215395898[11] = 0;
   out_1061295770215395898[12] = 0;
   out_1061295770215395898[13] = 0;
   out_1061295770215395898[14] = 0;
   out_1061295770215395898[15] = 0;
   out_1061295770215395898[16] = 0;
   out_1061295770215395898[17] = 0;
   out_1061295770215395898[18] = 0;
   out_1061295770215395898[19] = 0;
   out_1061295770215395898[20] = 0;
   out_1061295770215395898[21] = 0;
   out_1061295770215395898[22] = 0;
   out_1061295770215395898[23] = 0;
   out_1061295770215395898[24] = 0;
   out_1061295770215395898[25] = 1;
   out_1061295770215395898[26] = 0;
   out_1061295770215395898[27] = 0;
   out_1061295770215395898[28] = 0;
   out_1061295770215395898[29] = 0;
   out_1061295770215395898[30] = 0;
   out_1061295770215395898[31] = 0;
   out_1061295770215395898[32] = 0;
   out_1061295770215395898[33] = 0;
   out_1061295770215395898[34] = 0;
   out_1061295770215395898[35] = 0;
   out_1061295770215395898[36] = 0;
   out_1061295770215395898[37] = 0;
   out_1061295770215395898[38] = 0;
   out_1061295770215395898[39] = 0;
   out_1061295770215395898[40] = 0;
   out_1061295770215395898[41] = 0;
   out_1061295770215395898[42] = 0;
   out_1061295770215395898[43] = 0;
   out_1061295770215395898[44] = 1;
   out_1061295770215395898[45] = 0;
   out_1061295770215395898[46] = 0;
   out_1061295770215395898[47] = 0;
   out_1061295770215395898[48] = 0;
   out_1061295770215395898[49] = 0;
   out_1061295770215395898[50] = 0;
   out_1061295770215395898[51] = 0;
   out_1061295770215395898[52] = 0;
   out_1061295770215395898[53] = 0;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_2888912773465460112) {
  err_fun(nom_x, delta_x, out_2888912773465460112);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_5859204138557633979) {
  inv_err_fun(nom_x, true_x, out_5859204138557633979);
}
void pose_H_mod_fun(double *state, double *out_5221902563181446422) {
  H_mod_fun(state, out_5221902563181446422);
}
void pose_f_fun(double *state, double dt, double *out_1175449659287803657) {
  f_fun(state,  dt, out_1175449659287803657);
}
void pose_F_fun(double *state, double dt, double *out_1771814395118668150) {
  F_fun(state,  dt, out_1771814395118668150);
}
void pose_h_4(double *state, double *unused, double *out_6579517944273218715) {
  h_4(state, unused, out_6579517944273218715);
}
void pose_H_4(double *state, double *unused, double *out_626179243570512299) {
  H_4(state, unused, out_626179243570512299);
}
void pose_h_10(double *state, double *unused, double *out_1705430589688773801) {
  h_10(state, unused, out_1705430589688773801);
}
void pose_H_10(double *state, double *unused, double *out_7777681021109994334) {
  H_10(state, unused, out_7777681021109994334);
}
void pose_h_13(double *state, double *unused, double *out_5206051105996912215) {
  h_13(state, unused, out_5206051105996912215);
}
void pose_H_13(double *state, double *unused, double *out_2586094581761820502) {
  H_13(state, unused, out_2586094581761820502);
}
void pose_h_14(double *state, double *unused, double *out_9171638683540642626) {
  h_14(state, unused, out_9171638683540642626);
}
void pose_H_14(double *state, double *unused, double *out_1061295770215395898) {
  H_14(state, unused, out_1061295770215395898);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
